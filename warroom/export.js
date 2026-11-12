// Runs the page's own model (model.js) under Node.
//   node warroom/export.js <app_data.json>                  prints the bids/cut-risk JSON (bids.json), at 20,000 simulations
//   node warroom/export.js --calibrate <cases.json>         prints the raw rival-bid estimate for each past claim, and the
//                                                           rival-model inputs (target's projection, each rival's need)
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, 'model.js'), 'utf8');
const run = (D, expr) => { const ctx = vm.createContext({ D, Math, JSON, Object, Set, String }); vm.runInContext(src, ctx); return vm.runInContext(expr, ctx); };
if (process.argv[2] === '--calibrate') {
  const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const out = cases.map(c => { const ids = JSON.stringify(c.targets.map(t => t[0]));
    return { leg: c.leg, est: run(c.D, `rawEstimates(${ids})`), rival: run(c.D, `rivalInputs(${ids})`) }; });
  process.stdout.write(JSON.stringify(out) + '\n');
} else {
  process.stdout.write(JSON.stringify(run(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')), 'S.sims = 20000; exportBids()'), null, 1) + '\n');
}
