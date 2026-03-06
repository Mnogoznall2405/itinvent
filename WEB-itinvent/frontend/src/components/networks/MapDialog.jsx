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
    Typography,
} from '@mui/material';

export default function MapDialog({
    open,
    onClose,
    mapEditId,
    mapFile,
    setMapFile,
    mapTitle,
    setMapTitle,
    mapFloor,
    setMapFloor,
    mapSiteCode,
    setMapSiteCode,
    saveMap,
    sites = [],
}) {
    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <DialogTitle>{mapEditId ? 'Редактирование карты' : 'Загрузка карты'}</DialogTitle>
            <DialogContent>
                <Stack spacing={1.1} sx={{ mt: 0.5 }}>
                    {!mapEditId && (
                        <Button component="label" variant="outlined">
                            Выбрать файл
                            <input
                                hidden
                                type="file"
                                accept=".pdf,.PDF,.jpg,.jpeg,.png"
                                onChange={(event) => setMapFile(event.target.files?.[0] || null)}
                            />
                        </Button>
                    )}
                    {!mapEditId && (
                        <Typography variant="body2" color="text.secondary">
                            {mapFile?.name || 'Файл не выбран'}
                        </Typography>
                    )}
                    <TextField
                        label="Название"
                        value={mapTitle}
                        onChange={(event) => setMapTitle(event.target.value)}
                    />
                    <TextField
                        label="Этаж"
                        value={mapFloor}
                        onChange={(event) => setMapFloor(event.target.value)}
                    />
                    <TextField
                        select
                        label="Сайт"
                        value={mapSiteCode}
                        onChange={(event) => setMapSiteCode(event.target.value)}
                        helperText={!sites || sites.length === 0 ? "Сайты не загружены" : ""}
                    >
                        {(sites || []).map((site) => (
                            <MenuItem key={site.site_code} value={site.site_code}>
                                {site.name} ({site.site_code})
                            </MenuItem>
                        ))}
                    </TextField>
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Отмена</Button>
                <Button variant="contained" onClick={() => void saveMap()}>
                    Сохранить
                </Button>
            </DialogActions>
        </Dialog>
    );
}
