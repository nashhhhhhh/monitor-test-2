/* ===== REAL-TIME CLOCK ===== */
function updateClock() {
    const clock = document.getElementById('clock');
    if (!clock) return;

    const now = new Date();
    // Format: MON, 09 FEB, 15:33:02
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

    // Handles Dropdown highlighting (Utilities & Kitchen)
    document.querySelectorAll('.dropdown-menu a').forEach(link => {
        const linkPath = link.getAttribute('href').toLowerCase();
        if (path.includes(linkPath)) {
            // Find the parent button (e.g., "Utilities") and highlight it
            const parentBtn = link.closest('.nav-item')?.querySelector('.nav-btn');
            if (parentBtn) parentBtn.classList.add('active');
            link.classList.add('active-link');
        }
    });

    // 2. PDF EXPORT ENGINE
    const exportBtn = document.getElementById("export-report-btn");
    
    if (exportBtn) {
        exportBtn.addEventListener("click", async () => {
            // Visual feedback: Loading state
            const originalContent = exportBtn.innerHTML;
            exportBtn.disabled = true;
            exportBtn.innerHTML = `<span>⏳</span> GENERATING...`;

            try {
                console.log("📡 Requesting System PDF Report...");
                
                // Fetch the PDF from the Flask backend
                const response = await fetch('/api/export/report');
                
                if (!response.ok) {
                    throw new Error(`Server Error: ${response.status}`);
                }

                // Convert response to a blob
                const blob = await response.blob();
                
                // Create a download link and trigger it
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `SATS_Stage2_Report_${new Date().toISOString().split('T')[0]}.pdf`;
                
                document.body.appendChild(a);
                a.click();
                
                // Cleanup
                window.URL.revokeObjectURL(url);
                a.remove();
                
                console.log("✅ PDF Downloaded Successfully");

            } catch (error) {
                console.error("🔥 Export Failed:", error);
                alert("Could not generate report. Please ensure the backend server is running.");
            } finally {
                // Restore button
                exportBtn.disabled = false;
                exportBtn.innerHTML = originalContent;
            }
        });
    }
});


/* ===== PDF EXPORT ENGINE (Delegated Version) ===== */
document.addEventListener("click", async (event) => {
    // Check if the clicked element (or its parent) is our export button
    const exportBtn = event.target.closest("#export-report-btn");
    
    if (exportBtn) {
        console.log("📄 Export Triggered via Delegation");
        
        // 1. Visual feedback
        const originalContent = exportBtn.innerHTML;
        exportBtn.disabled = true;
        exportBtn.innerHTML = `<span>⏳</span> GENERATING...`;

        try {
            // 2. Fetch the report
            const response = await fetch('/api/export/report');
            
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }

            // 3. Process Download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `SATS_Report_${new Date().toISOString().split('T')[0]}.pdf`;
            
            document.body.appendChild(a);
            a.click();
            
            // 4. Cleanup
            window.URL.revokeObjectURL(url);
            a.remove();
            console.log("✅ PDF Downloaded");

        } catch (error) {
            console.error("🔥 Export Error:", error);
            alert("Export failed. Check terminal for backend errors.");
        } finally {
            // 5. Reset button
            exportBtn.disabled = false;
            exportBtn.innerHTML = originalContent;
        }
    }
});