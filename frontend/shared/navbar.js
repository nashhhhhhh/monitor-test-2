function updateClock() {
    const clock = document.getElementById('clock');
    if (!clock) return;

    const now = new Date();
    clock.innerText = now.toLocaleString('en-GB', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).toUpperCase();
}

setInterval(updateClock, 1000);
updateClock();

/* ===== ACTIVE NAV DETECTION ===== */
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname.toLowerCase();

    document.querySelectorAll('.nav-btn[data-nav]').forEach(btn => {
        const key = btn.dataset.nav;

        if (path.includes(key)) {
            btn.classList.add('active');
        }
    });
});
