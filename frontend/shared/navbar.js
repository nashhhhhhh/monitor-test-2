/* ===== REAL-TIME CLOCK ===== */
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

/* ===== NAVIGATION & EXPORT LOGIC ===== */
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname.toLowerCase();

    // 1. ACTIVE NAV DETECTION
    // Handles top-level buttons
    document.querySelectorAll('.nav-btn[data-nav]').forEach(btn => {
        const key = btn.dataset.nav;
        if (path.includes(key.toLowerCase())) {
            btn.classList.add('active');
        }
    });

    // Handles Dropdown highlighting
    document.querySelectorAll('.dropdown-menu a').forEach(link => {
        const linkPath = link.getAttribute('href').toLowerCase();
        if (path.includes(linkPath)) {
            const parentBtn = link.closest('.nav-item')?.querySelector('.nav-btn');
            if (parentBtn) parentBtn.classList.add('active');
            link.classList.add('active-link');
        }
    });
});

/* ===== PDF EXPORT ENGINE (DELEGATED) ===== */
// We use delegation so it works even if the navbar is loaded after the script runs
document.addEventListener("click", async (event) => {
    const exportBtn = event.target.closest("#export-report-btn");
    
    if (exportBtn) {
        event.preventDefault(); // Stop any default button behavior
        
        console.log("📄 Export Triggered");
        
        const originalContent = exportBtn.innerHTML;
        exportBtn.disabled = true;
        exportBtn.innerHTML = `<span>⏳</span> GENERATING...`;

        try {
            const response = await fetch('/api/export/report');
            
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || `Server Error: ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `SATS_Report_${new Date().toISOString().split('T')[0]}.pdf`;
            
            document.body.appendChild(a);
            a.click();
            
            window.URL.revokeObjectURL(url);
            a.remove();
            console.log("✅ PDF Downloaded");

        } catch (error) {
            console.error("🔥 Export Error:", error);
            alert("Export failed: " + error.message);
        } finally {
            exportBtn.disabled = false;
            exportBtn.innerHTML = originalContent;
        }
    }
});