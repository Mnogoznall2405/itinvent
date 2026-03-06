import React, { useRef } from 'react';

import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    MenuItem,
    Stack,
    TextField,
    Typography,
    Paper,
    IconButton,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';

export function CreateBranchDialog({
    open,
    onClose,
    createBranchDbId,
    setCreateBranchDbId,
    availableDatabases,
    createBranchName,
    setCreateBranchName,
    createBranchDefaultSiteCode,
    createPanelMode,
    setCreatePanelMode,
    createPanelCount,
    setCreatePanelCount,
    createPortsPerPanel,
    setCreatePortsPerPanel,
    createPanels,
    addPanel,
    removePanel,
    updatePanelIndex,
    updatePanelPortCount,
    createFillMode,
    setCreateFillMode,
    createTemplateFile,
    setCreateTemplateFile,
    createBranchSaving,
    createBranchWithProfile,
}) {
    const templateInputRef = useRef(null);

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>Создание филиала</DialogTitle>
            <DialogContent>
                <Stack spacing={1.2} sx={{ mt: 0.5 }}>
                    <TextField
                        select
                        label="База для синхронизации по MAC"
                        value={createBranchDbId}
                        onChange={(event) => setCreateBranchDbId(event.target.value)}
                        helperText="База данных для поиска IP/MAC/ФИО по MAC-адресу"
                        fullWidth
                        size="small"
                    >
                        <MenuItem value="">Не использовать</MenuItem>
                        {availableDatabases.map((db) => (
                            <MenuItem key={db.id} value={db.id}>
                                {db.name || db.id}
                            </MenuItem>
                        ))}
                    </TextField>

                    <TextField
                        label="Название филиала"
                        value={createBranchName}
                        onChange={(event) => setCreateBranchName(event.target.value)}
                        placeholder="Напр. Первомайская 19/21, Герцена 55"
                        helperText={`Код сайта: ${createBranchDefaultSiteCode || 'p19'} (генерируется автоматически)`}
                        fullWidth
                    />

                    {createFillMode !== "template" && (
                        <>
                            <TextField
                                select
                                label="Режим патч-панелей"
                        value={createPanelMode}
                        onChange={(event) => setCreatePanelMode(event.target.value)}
                    >
                        <MenuItem value="uniform">Одинаковые (Uniform)</MenuItem>
                        <MenuItem value="heterogeneous">Индивидуальные (Heterogeneous)</MenuItem>
                    </TextField>

                    {createPanelMode === 'uniform' ? (
                        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                            <TextField
                                type="number"
                                label="Кол-во патч-панелей"
                                value={createPanelCount}
                                onChange={(event) => setCreatePanelCount(event.target.value)}
                                inputProps={{ min: 1, max: 200 }}
                                fullWidth
                            />
                            <TextField
                                type="number"
                                label="Портов на панель"
                                value={createPortsPerPanel}
                                onChange={(event) => setCreatePortsPerPanel(event.target.value)}
                                inputProps={{ min: 1, max: 512 }}
                                fullWidth
                            />
                        </Stack>
                    ) : (
                        <Stack spacing={1}>
                            <Stack direction="row" spacing={1} alignItems="center">
                                <Typography variant="body2" color="text.secondary">
                                    Патч-панели ({createPanels.length})
                                </Typography>
                                <Button size="small" onClick={addPanel} disabled={createPanels.length >= 200}>
                                    + Добавить
                                </Button>
                            </Stack>
                            {createPanels.length === 0 && (
                                <Typography variant="body2" color="text.secondary">
                                    Нажмите &quot;Добавить&quot; чтобы создать патч-панель
                                </Typography>
                            )}
                            {createPanels.map((panel) => (
                                <Paper key={panel.id} sx={{ p: 1, display: 'flex', gap: 1, alignItems: 'center' }}>
                                    <TextField
                                        type="number"
                                        label="№"
                                        value={panel.panelIndex}
                                        onChange={(e) => updatePanelIndex(panel.id, e.target.value)}
                                        inputProps={{ min: 1, max: 200 }}
                                        sx={{ width: 80 }}
                                        size="small"
                                    />
                                    <TextField
                                        type="number"
                                        label="Портов"
                                        value={panel.portCount}
                                        onChange={(e) => updatePanelPortCount(panel.id, e.target.value)}
                                        inputProps={{ min: 1, max: 512 }}
                                        sx={{ width: 100 }}
                                        size="small"
                                    />
                                    <IconButton
                                        size="small"
                                        onClick={() => removePanel(panel.id)}
                                        disabled={createPanels.length <= 1}
                                        color="error"
                                    >
                                        <CloseIcon fontSize="small" />
                                    </IconButton>
                                </Paper>
                            ))}
                        </Stack>
                            )}
                        </>
                    )}

                    <TextField
                        select
                        label="Заполнение таблицы розеток"
                        value={createFillMode}
                        onChange={(event) => setCreateFillMode(event.target.value)}
                    >
                        <MenuItem value="manual">Ручное / пустая таблица</MenuItem>
                        <MenuItem value="template">Импорт из шаблона</MenuItem>
                    </TextField>

                    {createFillMode === 'template' && (
                        <>
                            <input
                                ref={templateInputRef}
                                hidden
                                type="file"
                                accept=".xlsx,.xlsm"
                                onChange={(event) => {
                                    setCreateTemplateFile(event.target.files?.[0] || null);
                                    event.target.value = '';
                                }}
                            />
                            <Button
                                variant="outlined"
                                onClick={() => setTimeout(() => templateInputRef.current?.click(), 0)}
                            >
                                Шаблон розеток (Excel)
                            </Button>
                            <Typography variant="body2" color="text.secondary">
                                {createTemplateFile?.name || 'Файл не выбран'}
                            </Typography>
                        </>
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Отмена</Button>
                <Button variant="contained" disabled={createBranchSaving} onClick={() => void createBranchWithProfile()}>
                    Создать
                </Button>
            </DialogActions>
        </Dialog>
    );
}



export function EditBranchDialog({
    open,
    onClose,
    branchEditName,
    setBranchEditName,
    branchDefaultSiteCode,
    setBranchDefaultSiteCode,
    branchEditDbId,
    setBranchEditDbId,
    branchEditLoading,
    availableDatabases,
    branchEditSaving,
    saveBranchEdit,
}) {
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>Редактирование филиала</DialogTitle>
            <DialogContent>
                <Stack spacing={1.5} sx={{ mt: 0.5 }}>
                    <TextField
                        label="Название филиала"
                        value={branchEditName}
                        onChange={(event) => setBranchEditName(event.target.value)}
                        placeholder="Напр. Санкт-Петербург Чапаева 15 офис 4-204"
                        fullWidth
                    />
                    <TextField
                        label="Код сайта (по умолчанию)"
                        value={branchDefaultSiteCode}
                        onChange={(event) => setBranchDefaultSiteCode(event.target.value)}
                        placeholder="Напр. p19, p21, g55"
                        helperText="Используется при создании устройств"
                        fullWidth
                    />
                    <TextField
                        select
                        label="База для синхронизации по MAC"
                        value={branchEditDbId}
                        onChange={(event) => setBranchEditDbId(event.target.value)}
                        helperText={branchEditDbId ? `Текущая база: ${branchEditDbId}` : 'Не использовать'}
                        fullWidth
                        size="small"
                        disabled={branchEditLoading}
                    >
                        <MenuItem value="">Не использовать</MenuItem>
                        {(availableDatabases || []).map((db) => (
                            <MenuItem key={db.id} value={db.id}>
                                {db.name || db.id}
                            </MenuItem>
                        ))}
                    </TextField>
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Отмена</Button>
                <Button
                    variant="contained"
                    disabled={branchEditSaving || branchEditLoading}
                    onClick={() => void saveBranchEdit()}
                    startIcon={<SaveIcon />}
                >
                    Сохранить
                </Button>
            </DialogActions>
        </Dialog>
    );
}

export function DeleteBranchDialog({
    open,
    onClose,
    branchDeleteName,
    branchDeleteSaving,
    confirmDeleteBranch,
}) {
    return (
        <Dialog open={open} onClose={onClose}>
            <DialogTitle>Подтверждение удаления</DialogTitle>
            <DialogContent>
                <Typography>
                    Вы уверены, что хотите удалить филиал <b>"{branchDeleteName}"</b>?
                </Typography>
                <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                    Внимание: Это действие удалит филиал и все связанные данные (устройства, порты, розетки, карты, точки).
                </Typography>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose} disabled={branchDeleteSaving}>
                    Отмена
                </Button>
                <Button
                    variant="contained"
                    color="error"
                    disabled={branchDeleteSaving}
                    onClick={() => void confirmDeleteBranch()}
                    startIcon={<DeleteIcon />}
                >
                    Удалить
                </Button>
            </DialogActions>
        </Dialog>
    );
}


