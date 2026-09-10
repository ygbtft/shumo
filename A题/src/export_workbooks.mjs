import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const project = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const manifest = JSON.parse(await fs.readFile(path.join(project, 'cache/export_manifest.json'), 'utf8'));
const requested = process.argv[2] || 'core';
const selected = manifest.filter(entry => requested === 'all' || (requested === 'core' ? !entry.filename.includes('_3h') : entry.filename === requested));
const destination = path.join(project, 'results/workbooks');
const previews = path.join(project, 'tmp/workbook_previews');
await fs.mkdir(destination, { recursive: true });
await fs.mkdir(previews, { recursive: true });

for (const entry of selected) {
  const workbook = Workbook.create();
  for (const definition of entry.sheets) {
    let rows = JSON.parse(await fs.readFile(path.join(project, definition.data), 'utf8'));
    const sheet = workbook.worksheets.add(definition.name);
    for (let start = 0; start < rows.length; start += 2048) {
      const batch = rows.slice(start, start + 2048);
      sheet.getRangeByIndexes(start, 0, batch.length, definition.columns).values = batch;
    }
    sheet.getRangeByIndexes(0, 0, definition.rows, definition.columns).format.font = { name: 'Microsoft YaHei', size: 10 };
    sheet.getRangeByIndexes(0, 0, 1, definition.columns).format = { fill: '#E7ECF2', font: { name: 'Microsoft YaHei', bold: true, size: 10 }, rowHeight: 28 };
    sheet.getRangeByIndexes(0, 0, definition.rows, 1).format.columnWidth = 25;
    sheet.getRangeByIndexes(0, 1, definition.rows, definition.columns - 1).format.columnWidth = 12;
    sheet.getRangeByIndexes(1, 1, definition.rows - 1, definition.columns - 1).setNumberFormat('0.0000');
    sheet.getRangeByIndexes(1, 0, definition.rows - 1, 1).setNumberFormat('0');
    sheet.freezePanes.freezeRows(1);
    sheet.freezePanes.freezeColumns(1);
    sheet.showGridLines = false;
    console.log(entry.filename, definition.name, definition.rows, definition.columns);
    const preview = await workbook.render({ sheetName: definition.name, range: `A1:${definition.columns >= 8 ? 'H' : 'B'}12`, scale: 1.5 });
    await fs.writeFile(path.join(previews, `${entry.filename}-${definition.name}.png`), new Uint8Array(await preview.arrayBuffer()));
    const check = await workbook.inspect({ kind: 'table', range: `${definition.name}!A1:D4`, include: 'values', tableMaxRows: 4, tableMaxCols: 4, maxChars: 1500 });
    console.log(check.ndjson);
    rows = null;
  }
  const notes = workbook.worksheets.add('说明');
  notes.getRange('A1:B6').values = [
    ['项目', '说明'],
    ['来源', 'A题附件1.xlsx和附件2.xlsx；物性按题目附录2至4'],
    ['方法', 'Kirchhoff积分通量、加密有限体积网格、BDF积分'],
    ['单位', '时间s；距离cm；温度摄氏度；水分kg/kg干基'],
    ['空白', '第四问中固定距离超过当前半径，表示该位置不在药材内部'],
    ['问题2范围', 'result2为完整干燥过程逐秒结果；result2_3h是前三小时的便捷节选'],
  ];
  notes.getRange('A1:B6').format.font = { name: 'Microsoft YaHei', size: 10 };
  notes.getRange('A:A').format.columnWidth = 18;
  notes.getRange('B:B').format.columnWidth = 80;
  notes.getRange('A1:B1').format.fill = '#E7ECF2';
  notes.getRange('A1:B6').format.wrapText = true;
  notes.getRange('A1:B6').format.rowHeight = 32;
  notes.showGridLines = false;
  const preview = await workbook.render({ sheetName: '说明', range: 'A1:B6', scale: 1.2 });
  await fs.writeFile(path.join(previews, `${entry.filename}-说明.png`), new Uint8Array(await preview.arrayBuffer()));
  const exported = await SpreadsheetFile.exportXlsx(workbook);
  await exported.save(path.join(destination, entry.filename));
  console.log('SAVED', entry.filename);
}
