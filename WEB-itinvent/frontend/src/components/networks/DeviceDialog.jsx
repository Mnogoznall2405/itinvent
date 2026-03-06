import React from 'react';
import {
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    MenuItem,
    Stack,
    TextField,
} from '@mui/material';

export default function DeviceDialog({
    open,
    onClose,
    deviceEditId,
    deviceCode,
    setDeviceCode,
    deviceType,
    setDeviceType,
    deviceSiteCode,
    setDeviceSiteCode,
    deviceVendor,
    setDeviceVendor,
    deviceModel,
    setDeviceModel,
    deviceMgmtIp,
    setDeviceMgmtIp,
    deviceSheetName,
    setDeviceSheetName,
    deviceNotes,
    setDeviceNotes,
    devicePortCount,
    setDevicePortCount,
    deviceSaving,
    saveDevice,
    deviceDeleting,
    deleteDevice,
}) {
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>
                {deviceEditId ? 'Редактирование оборудования' : 'Добавление оборудования'}
            </DialogTitle>
            <DialogContent>
                <Stack spacing={1.2} sx={{ mt: 0.5 }}>
                    <TextField
                        label="Код устройства *"
                        value={deviceCode}
                        onChange={(e) => setDeviceCode(e.target.value)}
                        placeholder="Напр. ASW-1"
                        disabled={!!deviceEditId}
                        fullWidth
                        size="small"
                    />
                    <TextField
                        select
                        label="Тип устройства *"
                        value={deviceType}
                        onChange={(e) => setDeviceType(e.target.value)}
                        fullWidth
                        size="small"
                    >
                        <MenuItem value="switch">Switch</MenuItem>
                        <MenuItem value="router">Router</MenuItem>
                        <MenuItem value="firewall">Firewall</MenuItem>
                        <MenuItem value="ap">Access Point</MenuItem>
                        <MenuItem value="other">Other</MenuItem>
                    </TextField>
                    <TextField
                        label="Код сайта"
                        value={deviceSiteCode}
                        onChange={(e) => setDeviceSiteCode(e.target.value)}
                        placeholder="Напр. p19, p21, g55"
                        helperText="Автоматически из филиала или введите вручную"
                        fullWidth
                        size="small"
                    />
                    <TextField
                        label="Производитель"
                        value={deviceVendor}
                        onChange={(e) => setDeviceVendor(e.target.value)}
                        placeholder="Напр. D-Link"
                        fullWidth
                        size="small"
                    />
                    <TextField
                        label="Модель"
                        value={deviceModel}
                        onChange={(e) => setDeviceModel(e.target.value)}
                        placeholder="Напр. DES-3200-28"
                        fullWidth
                        size="small"
                    />
                    <TextField
                        label="IP адрес управления"
                        value={deviceMgmtIp}
                        onChange={(e) => setDeviceMgmtIp(e.target.value)}
                        placeholder="10.0.0.1"
                        fullWidth
                        size="small"
                    />
                    <TextField
                        label="Имя листа (sheet_name)"
                        value={deviceSheetName}
                        onChange={(e) => setDeviceSheetName(e.target.value)}
                        placeholder="Напр. Лист1"
                        fullWidth
                        size="small"
                    />
                    <TextField
                        label="Заметки"
                        value={deviceNotes}
                        onChange={(e) => setDeviceNotes(e.target.value)}
                        multiline
                        rows={2}
                        fullWidth
                        size="small"
                    />
                    {!deviceEditId && (
                        <TextField
                            type="number"
                            label="Количество портов"
                            value={devicePortCount}
                            onChange={(e) => setDevicePortCount(e.target.value)}
                            placeholder="Напр. 28"
                            helperText="Если указано, порты будут созданы автоматически"
                            fullWidth
                            size="small"
                            inputProps={{ min: 1, max: 512 }}
                        />
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                {deviceEditId && (
                    <Button
                        color="error"
                        disabled={deviceDeleting}
                        onClick={() => void deleteDevice()}
                    >
                        Удалить
                    </Button>
                )}
                <Button onClick={onClose} disabled={deviceSaving || deviceDeleting}>
                    Отмена
                </Button>
                <Button
                    variant="contained"
                    disabled={deviceSaving || deviceDeleting}
                    onClick={() => void saveDevice()}
                >
                    {deviceEditId ? 'Сохранить' : 'Создать'}
                </Button>
            </DialogActions>
        </Dialog>
    );
}
