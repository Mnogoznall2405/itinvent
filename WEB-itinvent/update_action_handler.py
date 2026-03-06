import re

# Read the file
with open('frontend/src/pages/Database.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the old pattern - find the onClick handler in the action modal's confirm button
old_pattern = r'(onClick={async \(\) => \{[\s\S]*? \}\}\n              variant="contained"\n              disabled=\{actionLoading\}>\n              \{actionLoading \? \'Выполнение\.\.\. : \'Подтвердить\'\}\n            </Button>'

# Define the new onClick handler with real API calls
new_handler = '''onClick={async () => {
                setActionLoading(true);
                setActionError('');

                try {
                  const db_name = localStorage.getItem('selected_database') || '';
                  const branch = selectedBranch || '';

                  if (actionModal.type === 'transfer' && newEmployee.trim()) {
                    const items = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
                    
                    await jsonAPI.bulkTransfer({
                      items: items.map(invNo => {
                        const item = findEquipmentByInvNo(invNo);
                        return {
                          serial_number: item?.SERIAL_NO || item?.serial_no || '',
                          inv_no: invNo,
                          employee: item?.OWNER_DISPLAY_NAME || item?.employee_name || '',
                        };
                      }),
                      new_employee: newEmployee,
                      branch: branch,
                      location: '',
                      db_name: db_name,
                    });
                  } else if (actionModal.type === 'cartridge') {
                    if (!cartridgeColor) {
                      setActionError('Выберите цвет картриджа');
                      return;
                    }
                    
                    const items = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
                    
                    await jsonAPI.bulkWork({
                      work_type: 'cartridge',
                      items: items.map(invNo => {
                        const item = findEquipmentByInvNo(invNo);
                        return {
                          printer_model: item?.MODEL_NAME || item?.model_name || 'Unknown',
                          cartridge_color: cartridgeColor,
                          };
                      }),
                      cartridge_color: cartridgeColor,
                      branch: branch,
                      db_name: db_name,
                    });
                  } else if (actionModal.type === 'battery') {
                    const items = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
                    
                    await jsonAPI.bulkWork({
                      work_type: 'battery',
                      items: items.map(invNo => {
                        const item = findEquipmentByInvNo(invNo);
                        return {
                          serial_number: item?.SERIAL_NO || item?.serial_no || '',
                          };
                      }),
                      branch: branch,
                      db_name: db_name,
                    });
                  } else if (actionModal.type === 'component') {
                    if (!componentModel.trim()) {
                      setActionError('Введите модель компонента');
                      return;
                    }
                    
                    const items = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
                    
                    await jsonAPI.bulkWork({
                      work_type: 'component',
                      items: items.map(invNo => {
                        const item = findEquipmentByInvNo(invNo);
                        return {
                          serial_number: item?.SERIAL_NO || item?.serial_no || '',
                          component_type: componentType,
                          component_model: componentModel,
                          };
                      }),
                      component_type: componentType,
                      component_model: componentModel,
                      branch: branch,
                      db_name: db_name,
                    });
                  } else if (actionModal.type === 'cleaning') {
                    const items = selectedItems.length > 0 ? selectedItems : [actionModal.invNo];
                    
                    await jsonAPI.bulkWork({
                      work_type: 'cleaning',
                      items: items.map(invNo => {
                        const item = findEquipmentByInvNo(invNo);
                        return {
                          serial_number: item?.SERIAL_NO || item?.serial_no || '',
                          employee: item?.OWNER_DISPLAY_NAME || item?.employee_name || '',
                          };
                      }),
                      branch: branch,
                      db_name: db_name,
                    });
                  }

                  setActionModal({ open: false, type: null, invNo: null });
                  setSelectedItems([]);
                  setActionError('');
                  setNewEmployee('');
                  setCartridgeColor('');
                  setComponentType('fuser');
                  setComponentModel('');
                } catch (error) {
                  console.error('Action error:', error);
                  setActionError(error.response?.data?.detail || error.message || 'Ошибка выполнения операции');
                } finally {
                  setActionLoading(false);
                }
              }}
              variant="contained"
              disabled={actionLoading}
            >
              {actionLoading ? 'Выполнение...' : 'Подтвердить'}
            </Button>'''

# Replace old with new
new_content = re.sub(old_pattern, new_handler, content, count=1)

# Write the file
with open('frontend/src/pages/Database.jsx', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Action handler updated')
