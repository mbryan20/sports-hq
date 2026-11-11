// Try a move from the command line, with the page's own model and data (Q-054; the Ask Claude answerer uses it):
//   node warroom/trymove.js "Caleb Williams" "Dallas Goedert"                     add, drop
//   node warroom/trymove.js "Josh Jacobs" "Woody Marks" "Caleb Williams" ""       two moves; "" = let the model pick the drop
// Prints tryMove()'s result (win odds, weeks alive, cut risk, lineup by week, claim price, verdict and reasons) as JSON.
const fs = require('fs'), path = require('path'), vm = require('vm');
const D = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'war-room-v2', 'data.json'), 'utf8'));
const ctx = vm.createContext({ D, Math, JSON, Object, Set, String });
vm.runInContext(fs.readFileSync(path.join(__dirname, 'model.js'), 'utf8'), ctx);
const fold = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
const find = n => { if (!n) return null; const f = fold(n); const s = Object.keys(D.P).find(k => fold(D.P[k].n) === f); if (!s) throw new Error(`no player named "${n}" in the War Room data`); return s; };
const args = process.argv.slice(2), adds = [], drops = [];
for (let i = 0; i < args.length; i += 2) { adds.push(find(args[i])); drops.push(find(args[i + 1])); }
ctx.adds = adds; ctx.drops = drops;
const r = vm.runInContext('tryMove(adds, drops)', ctx);
process.stdout.write(JSON.stringify(r, null, 1) + '\n');
