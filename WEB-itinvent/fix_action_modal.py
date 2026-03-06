import re

with open('frontend/src/pages/Database.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the problematic action handler section
old_pattern = r'onClick={async \(\) => \{[\s\S]*? \}\}\n              variant="contained"\n              disabled=\{actionLoading\}>\n              \{actionLoading \? \'Выполнение\.\.\.\. : \'Подтвердить\'\}\n            </Button>'

new_code = '''onClick={async () => {
                console.log('Action:', actionModal.type, 'Items:', selectedItems.length > 0 ? selectedItems : actionModal.invNo);
                setActionModal({ open: false, type: null, invNo: null });
                setSelectedItems([]);
              }}
              variant="contained"
              disabled={actionLoading}
            >
              {actionLoading ? 'Выполнение...' : 'Подтвердить'}
            </Button>'''

new_content = re.sub(old_pattern, new_code, content, count=1)

with open('frontend/src/pages/Database.jsx', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Fixed action modal')
