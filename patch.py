import pathlib
p = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\frontend\src\components\networks\BranchDialogs.jsx')
c = p.read_text(encoding='utf-8')
c = c.replace('<TextField\n                        select\n                        label="Режим патч-панелей"', '{createFillMode !== "template" && (\n                        <>\n                            <TextField\n                                select\n                                label="Режим патч-панелей"')
c = c.replace('</Stack>\n                    )}\n\n                    <TextField\n                        select\n                        label="Заполнение', '</Stack>\n                            )}\n                        </>\n                    )}\n\n                    <TextField\n                        select\n                        label="Заполнение')
p.write_text(c, encoding='utf-8')

p2 = pathlib.Path(r'c:\Project\Image_scan\WEB-itinvent\frontend\src\pages\Networks.jsx')
c2 = p2.read_text(encoding='utf-8')
old_payload = """    if (createPanelMode === 'uniform') {
      const panelCount = Number(createPanelCount || 0);
      const portsPerPanel = Number(createPortsPerPanel || 0);
      if (!panelCount || !portsPerPanel) {
        notifyError('Укажите профиль патч-панелей.');
        return;
      }
      payload.panel_count = panelCount;
      payload.ports_per_panel = portsPerPanel;
    } else {
      // heterogeneous mode
      if (!createPanels || createPanels.length === 0) {
        notifyError('Добавьте хотя бы одну патч-панель.');
        return;
      }
      payload.panels = createPanels.map(p => ({
        panel_index: Number(p.panelIndex),
        port_count: Number(p.portCount),
      }));
    }"""
new_payload = """    if (createFillMode !== 'template') {
      if (createPanelMode === 'uniform') {
        const panelCount = Number(createPanelCount || 0);
        const portsPerPanel = Number(createPortsPerPanel || 0);
        if (!panelCount || !portsPerPanel) {
          notifyError('Укажите профиль патч-панелей.');
          return;
        }
        payload.panel_count = panelCount;
        payload.ports_per_panel = portsPerPanel;
      } else {
        // heterogeneous mode
        if (!createPanels || createPanels.length === 0) {
          notifyError('Добавьте хотя бы одну патч-панель.');
          return;
        }
        payload.panels = createPanels.map(p => ({
          panel_index: Number(p.panelIndex),
          port_count: Number(p.portCount),
        }));
      }
    }"""
c2 = c2.replace(old_payload, new_payload)
p2.write_text(c2, encoding='utf-8')
