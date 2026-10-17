"""Telegram message formatting and notification templates."""

from __future__ import annotations

from datetime import datetime
import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.checker import CheckResult
    from src.state import StateManager, TargetState


def escape(text: str | None) -> str:
    """Escape text for Telegram HTML formatting."""
    if not text:
        return ""
    return html.escape(str(text))


def format_timestamp(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%d-%m-%Y %H:%M:%S WIB")


def format_down_alert(result: CheckResult, state: TargetState, threshold: int) -> str:
    """Format emergency DOWN alert notification."""
    target_esc = escape(result.target)
    err_esc = escape(result.error_message or "Server tidak dapat diakses")
    time_str = format_timestamp(result.checked_at)

    return (
        f"🚨 <b>PERINGATAN: SERVER CPANEL DOWN!</b>\n\n"
        f"🎯 <b>Target:</b> <code>{target_esc}</code>\n"
        f"❌ <b>Penyebab / Status:</b> <code>{err_esc}</code>\n"
        f"🔄 <b>Status Deteksi:</b> Gagal {state.consecutive_failures}x berturut-turut (ambang batas: {threshold}x)\n"
        f"🕒 <b>Waktu Kejadian:</b> {time_str}\n\n"
        f"⚡ <b>Aksi Cepat:</b>\n"
        f"<i>Segera hubungi admin pemilik server agar server/service dapat dinyalakan kembali!</i>"
    )


def format_reminder_alert(result: CheckResult, state: TargetState, downtime_duration: str) -> str:
    """Format periodic reminder while server remains DOWN."""
    target_esc = escape(result.target)
    err_esc = escape(result.error_message or "Masih tidak dapat dihubungi")
    time_str = format_timestamp(result.checked_at)

    return (
        f"⚠️ <b>PENGINGAT: SERVER MASIH DOWN</b>\n\n"
        f"🎯 <b>Target:</b> <code>{target_esc}</code>\n"
        f"⏳ <b>Durasi Downtime:</b> <b>{escape(downtime_duration)}</b>\n"
        f"❌ <b>Status Terakhir:</b> <code>{err_esc}</code>\n"
        f"🕒 <b>Waktu Cek:</b> {time_str}\n\n"
        f"<i>Server belum pulih. Pastikan admin server sudah menerima informasi ini.</i>"
    )


def format_recovered_alert(result: CheckResult, state: TargetState, downtime_duration: str) -> str:
    """Format RECOVERY notification when server comes back online."""
    target_esc = escape(result.target)
    code_str = f"HTTP {result.status_code}" if result.status_code else "Koneksi Berhasil"
    time_str = format_timestamp(result.checked_at)

    return (
        f"✅ <b>PEMULIHAN: SERVER TELAH AKTIF KEMBALI!</b>\n\n"
        f"🎯 <b>Target:</b> <code>{target_esc}</code>\n"
        f"🟢 <b>Status:</b> <b>{code_str}</b> (Latency: {result.latency_ms:.0f} ms)\n"
        f"⏱ <b>Total Waktu Down:</b> <b>{escape(downtime_duration)}</b>\n"
        f"🕒 <b>Waktu Pulih:</b> {time_str}\n\n"
        f"<i>Layanan sudah dapat diakses dengan normal kembali.</i>"
    )


def format_status_report(
    results: list[CheckResult],
    state_mgr: StateManager,
    interval_seconds: int,
    threshold: int,
) -> str:
    """Format status report for /status or /check command."""
    time_str = format_timestamp()
    is_muted, mute_left = state_mgr.is_muted()

    lines = [
        "📊 <b>LAPORAN STATUS KESEHATAN SERVER</b>",
        f"🕒 <i>Waktu: {time_str}</i>",
        f"⏱ <i>Interval Cek: {interval_seconds} detik (Toleransi: {threshold}x)</i>",
    ]

    if is_muted:
        lines.append(f"🔇 <i>Alert sedang di-MUTE (sisa: {mute_left})</i>")

    lines.append("")

    if not results:
        lines.append("⚠️ <i>Belum ada URL target yang dipantau. Tambahkan dengan /addtarget</i>")
        return "\n".join(lines)

    for idx, res in enumerate(results, start=1):
        target_state = state_mgr.get_or_create_state(res.target)
        if res.is_up:
            icon = "🟢"
            status_text = f"<b>ONLINE</b> ({res.status_summary})"
        else:
            if target_state.is_confirmed_down:
                icon = "🔴"
                duration = format_duration(target_state.calculate_current_downtime_seconds())
                status_text = f"<b>DOWN</b> ({res.status_summary}) - Down: {duration}"
            else:
                icon = "🟡"
                status_text = f"<b>FAILING</b> ({target_state.consecutive_failures}/{threshold}x)"

        lines.append(f"{idx}. {icon} <code>{escape(res.target)}</code>")
        lines.append(f"   └ Status: {status_text}")
        if res.error_message and not res.is_up:
            lines.append(f"   └ Error: <i>{escape(res.error_message)}</i>")

    return "\n".join(lines)


def format_help_message() -> str:
    """Format help command text."""
    return (
        "🤖 <b>PANDUAN PERINTAH CPANEL MONITOR BOT</b>\n\n"
        "<b>Pemantauan Status:</b>\n"
        "• /status — Cek status kesehatan seluruh target & latency\n"
        "• /check — Jalankan pengecekan manual instan sekarang\n\n"
        "<b>Kelola Target & Frekuensi:</b>\n"
        "• /targets — Lihat daftar URL target & interval aktif\n"
        "• /addtarget &lt;url&gt; — Tambah URL target pemantauan baru\n"
        "  <i>Contoh: /addtarget https://prima.rsmra.id:2083</i>\n"
        "• /removetarget &lt;url&gt; — Hapus URL dari pemantauan\n"
        "• /setinterval &lt;detik&gt; — Ubah frekuensi cek (detik)\n"
        "  <i>Contoh: /setinterval 30 (minimal 5 detik)</i>\n"
        "• /setthreshold &lt;kali&gt; — Ubah ambang batas toleransi gagal\n"
        "  <i>Contoh: /setthreshold 3</i>\n\n"
        "<b>Kontrol Notifikasi:</b>\n"
        "• /mute &lt;menit&gt; — Jeda notifikasi alert (misal saat maintenance)\n"
        "  <i>Contoh: /mute 60 (jeda selama 1 jam)</i>\n"
        "• /unmute — Aktifkan kembali notifikasi alert\n"
        "• /help — Tampilkan pesan panduan ini\n\n"
        "💡 <i>Tip: Semua perubahan target & interval otomatis tersimpan secara permanen.</i>"
    )
