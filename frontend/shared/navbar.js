function updateClock() {
    const clockElement = document.getElementById('clock');
    if (!clockElement) return;

    const now = new Date();
    const options = { 
        weekday: 'short', 
        day: '2-digit', 
        month: 'short', 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit', 
        hour12: false 
    };
    
    // Formats to: WED, 04 FEB, 08:49:03
    clockElement.innerText = now.toLocaleString('en-GB', options).toUpperCase();
}

// Start clock and update every second
setInterval(updateClock, 1000);
updateClock();
