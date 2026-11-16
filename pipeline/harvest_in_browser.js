// Paste in the browser console on https://psi.nasa.gov (any page). Downloads psi_bundle_metadata_tables.json
(async () => {
  const s = await fetch('/geode-py/ws/repo/search?term=combustion&source=psi&type=investigation&size=100').then(r => r.json());
  const ids = s.hits.hits.map(h => h._source).filter(x => x['Research Area'] === 'Combustion Science').map(x => x.Accession);
  const bundle = { harvested: new Date().toISOString(), search: s, investigations: {}, tables: {} };
  for (const id of ids) {
    const d = await fetch('/geode-py/ws/repo/investigations/' + id).then(r => r.json());
    bundle.investigations[id] = d;
    for (const t of (d.experimentalTable || [])) {
      const u = await fetch(`/geode-py/ws/studies/${id}/download?file=${encodeURIComponent(t.file_name)}&version=${t.version}&redirect=false`).then(r => r.text());
      bundle.tables[t.file_name] = await fetch(u).then(r => r.text());
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(bundle)], { type: 'application/json' }));
  a.download = 'psi_bundle_metadata_tables.json'; a.click();
  console.log('done', ids.length, Object.keys(bundle.tables).length);
})();
