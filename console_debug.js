// Paste this in browser Console (F12 → Console) on goofish.com
// It logs all form elements including those inside iframes

console.log("=== GOOFISH DEBUG (with iframes) ===");

function debugFrame(doc, label) {
    console.log(`\n--- ${label} ---`);

    doc.querySelectorAll('input, textarea').forEach((el, i) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && el.offsetParent !== null) {
            let sel = '';
            if (el.id) sel = '#' + el.id;
            else if (el.name) sel = `[name="${el.name}"]`;
            else if (el.placeholder) sel = `[placeholder="${el.placeholder}"]`;
            else sel = el.tagName.toLowerCase() + '.' + (el.className || '').split(' ')[0];
            console.log(`  [INPUT] ${sel}`, {type: el.type, placeholder: el.placeholder, value: el.value, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
        }
    });

    doc.querySelectorAll('button, [role="button"]').forEach((el, i) => {
        const r = el.getBoundingClientRect();
        const t = (el.textContent || '').trim().substring(0, 50);
        if (r.width > 0 && el.offsetParent !== null && t) {
            console.log(`  [BTN] <${el.tagName}> "${t}"`, {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
        }
    });

    doc.querySelectorAll('span, div, a').forEach(el => {
        const t = (el.textContent || '').trim();
        if (/^\+\d{1,4}$/.test(t) && el.offsetParent !== null) {
            const r = el.getBoundingClientRect();
            console.log(`  [COUNTRY] <${el.tagName}> "${t}" class="${el.className}"`, {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
        }
    });
}

// Debug main page
debugFrame(document, "MAIN PAGE");

// Debug all iframes
document.querySelectorAll('iframe').forEach((iframe, i) => {
    try {
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        debugFrame(doc, `IFRAME ${i}: ${iframe.src}`);
    } catch(e) {
        console.log(`  [IFRAME ${i}] CROSS-ORIGIN: ${iframe.src} (cannot access)`);
    }
});

// Click logger
document.addEventListener('click', (e) => {
    const el = e.target;
    const r = el.getBoundingClientRect();
    let sel = '';
    if (el.id) sel = '#' + el.id;
    else if (el.className) sel = el.tagName + '.' + (el.className||'').split(' ')[0];
    else sel = el.tagName;
    console.log(`[CLICK] ${sel} "${(el.textContent||'').trim().substring(0,40)}"`, {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)});
}, true);

console.log("\n=== Click around! Every click logs selector ===");
console.log("If you see CROSS-ORIGIN iframes, the login form is inside one.");
