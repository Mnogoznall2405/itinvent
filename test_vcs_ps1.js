const fs = require('fs');
const content = fs.readFileSync('c:\\Project\\Image_scan\\WEB-itinvent\\frontend\\src\\api\\vcs.js', 'utf8');
const match = content.match(/const ps1Script = \[\s*([\s\S]*?)\s*\]\.join\('/);
if (match) {
    const arrStr = '[' + match[1] + ']';
    try {
        const arr = eval(arrStr);
        console.log(arr.join('\r\n'));
    } catch (e) {
        console.error("Eval error", e);
    }
}
