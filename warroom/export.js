// Runs the page's own model (model.js) under Node and prints the bids/cut-risk JSON.
// Usage: node warroom/export.js <app_data.json>
const fs = require('fs'), path = require('path'), vm = require('vm');
const ctx = vm.createContext({ D: JSON.parse(fs.readFileSync(process.argv[2], 'utf8')), Math, JSON, Object, Set, String });
vm.runInContext(fs.readFileSync(path.join(__dirname, 'model.js'), 'utf8'), ctx);
process.stdout.write(JSON.stringify(vm.runInContext('exportBids()', ctx), null, 1) + '\n');
