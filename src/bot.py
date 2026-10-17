"""Main Telegram Bot runner and asynchronous monitoring service for cPanel."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import logging
from pathlib import Path
import sys

# Ensure project root is in sys.path so 'src' can be imported cleanly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from src.checker import check_all_targets
from src.config import ConfigManager
from src.notifier import (
    format_down_alert,
    format_help_message,
    format_recovered_alert,
    format_reminder_alert,
    format_status_report,
)
from src.state import AlertAction, StateManager

# Configure root logger
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("cpanel_monitor.bot")


class CPanelMonitorBot:
    """Orchestrates Telegram bot interface and background health monitoring loop."""

    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self.state_mgr = StateManager()
        self.monitor_task: asyncio.Task[None] | None = None
        self._is_running = True

    async def broadcast_message(self, bot, text: str) -> None:
        """Send a notification message to all configured admin chat IDs."""
        if not self.config.admin_chat_ids:
            logger.warning("No TELEGRAM_CHAT_ID configured. Notification suppressed:\n%s", text)
            return

        for chat_id in self.config.admin_chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except TelegramError as e:
                logger.error("Failed to send message to chat_id %s: %s", chat_id, e)

    # ========================================================
    # TELEGRAM COMMAND HANDLERS
    # ========================================================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command. Welcomes user and displays Chat ID."""
        chat = update.effective_chat
        if not chat:
            return

        chat_id = chat.id
        is_first_admin = False

        # If no admin IDs are set yet, auto-register this user
        if not self.config.admin_chat_ids:
            self.config.add_admin_chat_id(chat_id)
            is_first_admin = True

        welcome_text = (
            f"👋 <b>Halo! Bot Pemantau Server cPanel Aktif.</b>\n\n"
            f"🆔 <b>Chat ID Anda:</b> <code>{chat_id}</code>\n"
        )

        if is_first_admin:
            welcome_text += (
                "⭐️ <i>Chat ID Anda telah didaftarkan sebagai Admin utama.</i>\n"
                "<i>(Masukkan Chat ID ini ke file .env TELEGRAM_CHAT_ID agar permanen).</i>\n\n"
            )

        welcome_text += (
            "Gunakan /status untuk melihat kesehatan server, atau /help untuk melihat seluruh perintah."
        )

        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await update.message.reply_text(format_help_message(), parse_mode=ParseMode.HTML)

    async def cmd_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /id or /myid command to easily discover Telegram Chat ID."""
        chat = update.effective_chat
        if chat:
            await update.message.reply_text(
                f"🆔 <b>Chat ID Anda:</b> <code>{chat.id}</code>",
                parse_mode=ParseMode.HTML,
            )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command. Displays current health status of all targets."""
        targets = self.config.get_targets()
        if not targets:
            await update.message.reply_text(
                "⚠️ Belum ada target yang dipantau. Gunakan /addtarget <url> untuk menambahkan.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Fetch latest cached results from StateManager or trigger a quick check
        cached_results = []
        for t in targets:
            state = self.state_mgr.get_or_create_state(t)
            if state.last_result:
                cached_results.append(state.last_result)

        if not cached_results:
            # If no cached results yet, run instant check
            wait_msg = await update.message.reply_text("⏳ Memeriksa status server saat ini...")
            cached_results = await check_all_targets(targets, timeout=self.config.request_timeout_seconds)
            try:
                await wait_msg.delete()
            except TelegramError:
                pass

        report = format_status_report(
            cached_results,
            self.state_mgr,
            self.config.check_interval_seconds,
            self.config.failure_threshold,
        )
        await update.message.reply_text(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /check command. Forces an immediate real-time check of all targets."""
        targets = self.config.get_targets()
        if not targets:
            await update.message.reply_text("⚠️ Daftar target masih kosong. Tambahkan dengan /addtarget <url>.")
            return

        wait_msg = await update.message.reply_text(f"⏳ Sedang mengecek {len(targets)} target secara real-time...")
        results = await check_all_targets(targets, timeout=self.config.request_timeout_seconds)

        # Update states with the real-time results
        for res in results:
            self.state_mgr.process_result(
                res,
                self.config.failure_threshold,
                self.config.reminder_interval_minutes,
            )

        report = format_status_report(
            results,
            self.state_mgr,
            self.config.check_interval_seconds,
            self.config.failure_threshold,
        )
        try:
            await wait_msg.edit_text(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except TelegramError:
            await update.message.reply_text(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def cmd_targets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /targets command. Lists all monitored targets and current settings."""
        targets = self.config.get_targets()
        lines = [
            "📋 <b>DAFTAR TARGET PEMANTAUAN</b>\n",
            f"⏱ <b>Interval Pengecekan:</b> {self.config.check_interval_seconds} detik",
            f"🛡 <b>Toleransi Kegagalan:</b> {self.config.failure_threshold} kali berturut-turut",
            f"🔔 <b>Pengingat Down:</b> Tiap {self.config.reminder_interval_minutes} menit\n",
        ]

        if not targets:
            lines.append("<i>Tidak ada target aktif. Tambahkan dengan /addtarget &lt;url&gt;</i>")
        else:
            lines.append("<b>URL Target Terdaftar:</b>")
            for i, t in enumerate(targets, start=1):
                lines.append(f"{i}. <code>{t}</code>")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_add_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /addtarget <url> command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengubah konfigurasi.")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Masukkan URL target.\nContoh: <code>/addtarget https://prima.rsmra.id:2083</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        raw_url = context.args[0]
        success, message = self.config.add_target(raw_url)

        if success:
            await update.message.reply_text(
                f"✅ Target berhasil ditambahkan:\n<code>{message}</code>\n"
                f"Target ini akan langsung masuk dalam antrean pemantauan.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"❌ Gagal: {message}")

    async def cmd_remove_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /removetarget <url> command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengubah konfigurasi.")
            return

        if not context.args:
            await update.message.reply_text(
                "⚠️ Masukkan URL target yang ingin dihapus.\nContoh: <code>/removetarget https://prima.rsmra.id</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        raw_url = context.args[0]
        success, message = self.config.remove_target(raw_url)

        if success:
            self.state_mgr.remove_target(message)
            await update.message.reply_text(
                f"🗑 Target berhasil dihapus dari pemantauan:\n<code>{message}</code>",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(f"❌ Gagal: {message}")

    async def cmd_set_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setinterval <seconds> command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengubah konfigurasi.")
            return

        if not context.args:
            await update.message.reply_text(
                f"⚠️ Masukkan interval dalam detik (minimal 5 detik).\n"
                f"Interval saat ini: <b>{self.config.check_interval_seconds} detik</b>.\n"
                f"Contoh: <code>/setinterval 30</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            seconds = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Nilai interval harus berupa angka bulat.")
            return

        success, message = self.config.set_interval(seconds)
        if success:
            await update.message.reply_text(f"✅ {message}\nPerubahan langsung diterapkan sekarang.")
        else:
            await update.message.reply_text(f"❌ Gagal: {message}")

    async def cmd_set_threshold(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /setthreshold <count> command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengubah konfigurasi.")
            return

        if not context.args:
            await update.message.reply_text(
                f"⚠️ Masukkan jumlah kegagalan berturut-turut.\n"
                f"Threshold saat ini: <b>{self.config.failure_threshold} kali</b>.\n"
                f"Contoh: <code>/setthreshold 3</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            val = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Nilai threshold harus berupa angka bulat.")
            return

        success, message = self.config.set_threshold(val)
        if success:
            await update.message.reply_text(f"✅ {message}")
        else:
            await update.message.reply_text(f"❌ Gagal: {message}")

    async def cmd_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /mute <minutes> command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin untuk mengubah konfigurasi.")
            return

        minutes = 30  # default
        if context.args:
            try:
                minutes = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ Menit harus berupa angka. Contoh: /mute 60")
                return

        until = self.state_mgr.mute(minutes)
        until_str = until.strftime("%H:%M:%S WIB")
        await update.message.reply_text(
            f"🔇 <b>Notifikasi Alert Di-Mute</b>\n"
            f"Semua notifikasi alarm DOWN dihentikan sementara selama <b>{minutes} menit</b> (sampai {until_str}).\n"
            f"Gunakan /unmute untuk mengaktifkan kembali lebih awal.",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /unmute command."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.config.is_authorized(chat_id):
            await update.message.reply_text("⛔ Anda tidak memiliki izin.")
            return

        self.state_mgr.unmute()
        await update.message.reply_text(
            "🔔 <b>Notifikasi Alert Aktif Kembali!</b>\n"
            "Anda akan segera menerima pemberitahuan jika ada server yang terdeteksi DOWN.",
            parse_mode=ParseMode.HTML,
        )

    # ========================================================
    # BACKGROUND MONITOR LOOP
    # ========================================================

    async def run_monitor_cycle(self, bot) -> None:
        """Perform one monitoring cycle across all configured targets."""
        targets = self.config.get_targets()
        if not targets:
            return

        results = await check_all_targets(targets, timeout=self.config.request_timeout_seconds)

        for res in results:
            action, state, details = self.state_mgr.process_result(
                res,
                threshold=self.config.failure_threshold,
                reminder_minutes=self.config.reminder_interval_minutes,
            )

            if action == AlertAction.TRIGGER_DOWN:
                logger.warning("ALERT DOWN: %s (Failed %dx)", res.target, state.consecutive_failures)
                msg = format_down_alert(res, state, self.config.failure_threshold)
                await self.broadcast_message(bot, msg)

            elif action == AlertAction.REMINDER_DOWN:
                logger.info("REMINDER DOWN: %s (Still down: %s)", res.target, details)
                msg = format_reminder_alert(res, state, details)
                await self.broadcast_message(bot, msg)

            elif action == AlertAction.TRIGGER_RECOVERED:
                logger.info("RECOVERED: %s (Downtime: %s)", res.target, details)
                msg = format_recovered_alert(res, state, details)
                await self.broadcast_message(bot, msg)

    async def background_monitor_worker(self, bot) -> None:
        """Continuous background task checking server health at dynamic interval."""
        logger.info("Background monitoring worker started.")
        # Short initial delay to let bot finish starting
        await asyncio.sleep(2)

        while self._is_running:
            try:
                await self.run_monitor_cycle(bot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Unexpected error in monitoring cycle: %s", e)

            # Sleep for the configured interval (dynamically adapts when updated via /setinterval)
            sleep_duration = max(5, self.config.check_interval_seconds)
            try:
                await asyncio.sleep(sleep_duration)
            except asyncio.CancelledError:
                break

        logger.info("Background monitoring worker stopped.")

    async def on_post_init(self, app: Application) -> None:
        """Hook called after Application is initialized to launch background worker."""
        self.monitor_task = asyncio.create_task(self.background_monitor_worker(app.bot))

    async def on_shutdown(self, app: Application) -> None:
        """Gracefully cancel monitoring task on bot shutdown."""
        self._is_running = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass


def build_application(bot_instance: CPanelMonitorBot) -> Application:
    """Build and configure the Telegram Application instance."""
    app = (
        ApplicationBuilder()
        .token(bot_instance.config.bot_token)
        .post_init(bot_instance.on_post_init)
        .post_shutdown(bot_instance.on_shutdown)
        .build()
    )

    # Register command handlers
    app.add_handler(CommandHandler("start", bot_instance.cmd_start))
    app.add_handler(CommandHandler("help", bot_instance.cmd_help))
    app.add_handler(CommandHandler(["id", "myid"], bot_instance.cmd_id))
    app.add_handler(CommandHandler("status", bot_instance.cmd_status))
    app.add_handler(CommandHandler("check", bot_instance.cmd_check))
    app.add_handler(CommandHandler("targets", bot_instance.cmd_targets))
    app.add_handler(CommandHandler("addtarget", bot_instance.cmd_add_target))
    app.add_handler(CommandHandler("removetarget", bot_instance.cmd_remove_target))
    app.add_handler(CommandHandler("setinterval", bot_instance.cmd_set_interval))
    app.add_handler(CommandHandler("setthreshold", bot_instance.cmd_set_threshold))
    app.add_handler(CommandHandler("mute", bot_instance.cmd_mute))
    app.add_handler(CommandHandler("unmute", bot_instance.cmd_unmute))

    return app


async def run_check_once(config: ConfigManager) -> int:
    """Run a single check of all targets and print results to terminal."""
    targets = config.get_targets()
    print("=========================================================")
    print("  cPanel & Server Monitor - CLI Single Check")
    print(f"  Target count: {len(targets)} | Timeout: {config.request_timeout_seconds}s")
    print("=========================================================")

    if not targets:
        print("[!] No target URLs configured.")
        return 1

    results = await check_all_targets(targets, timeout=config.request_timeout_seconds)
    all_up = True
    for res in results:
        status_sym = "[OK]  " if res.is_up else "[FAIL]"
        print(f"{status_sym} {res.target} -> {res.status_summary}")
        if not res.is_up:
            all_up = False

    print("=========================================================")
    return 0 if all_up else 2


async def send_test_message(config: ConfigManager) -> int:
    """Send a test message to verify Telegram Bot token and chat ID."""
    if not config.bot_token:
        print("[ERROR] TELEGRAM_BOT_TOKEN is not configured in .env!")
        return 1
    if not config.admin_chat_ids:
        print("[ERROR] TELEGRAM_CHAT_ID is not configured in .env!")
        return 1

    from telegram import Bot

    bot = Bot(token=config.bot_token)
    test_text = (
        "🔔 <b>TES KONEKSI CPANEL MONITOR BOT BERHASIL</b>\n\n"
        f"Waktu: {datetime.now().strftime('%d-%m-%Y %H:%M:%S WIB')}\n"
        f"Target Aktif ({len(config.get_targets())}):\n"
        + "\n".join(f"• <code>{t}</code>" for t in config.get_targets())
        + "\n\n<i>Bot siap memantau server cPanel Anda 24/7!</i>"
    )

    print(f"Mengirim pesan tes ke chat IDs: {config.admin_chat_ids}...")
    success = True
    for cid in config.admin_chat_ids:
        try:
            await bot.send_message(
                chat_id=cid,
                text=test_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            print(f" -> Berhasil terkirim ke Chat ID: {cid}")
        except Exception as e:
            print(f" -> Gagal mengirim ke {cid}: {e}")
            success = False

    return 0 if success else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="cPanel & Server Monitor Telegram Bot")
    parser.add_argument("--check-once", action="store_true", help="Run a single check and print to console")
    parser.add_argument("--test-message", action="store_true", help="Send a test message to Telegram Chat ID")
    args = parser.parse_args()

    config = ConfigManager()

    if args.check_once:
        sys.exit(asyncio.run(run_check_once(config)))

    if args.test_message:
        sys.exit(asyncio.run(send_test_message(config)))

    # Running as full daemon bot
    if not config.bot_token or config.bot_token == "your_telegram_bot_token_here":
        print("=========================================================")
        print("  [PERINGATAN] TOKEN TELEGRAM BELUM DIKONFIGURASI")
        print("=========================================================")
        print("Silakan buka file .env dan isi token bot Telegram Anda:")
        print("  1. Buka @BotFather di Telegram lalu ketik /newbot")
        print("  2. Salin token bot yang diberikan")
        print("  3. Masukkan ke file .env pada baris TELEGRAM_BOT_TOKEN=")
        print("=========================================================")
        print("Untuk menguji kesehatan server tanpa bot, Anda bisa jalankan:")
        print("  python3 src/bot.py --check-once")
        print("=========================================================")
        sys.exit(1)

    print("=========================================================")
    print("  Menjalankan cPanel Monitor Telegram Bot (24/7 Daemon)")
    print(f"  Target terdaftar ({len(config.get_targets())}):")
    for t in config.get_targets():
        print(f"   • {t}")
    print(f"  Interval pengecekan: {config.check_interval_seconds} detik")
    print(f"  Toleransi kegagalan : {config.failure_threshold} kali")
    print(f"  Admin Chat ID       : {config.admin_chat_ids or 'Belum diset (akan terdaftar saat /start)'}")
    print("=========================================================")

    bot_instance = CPanelMonitorBot(config)
    application = build_application(bot_instance)

    # Start polling
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
