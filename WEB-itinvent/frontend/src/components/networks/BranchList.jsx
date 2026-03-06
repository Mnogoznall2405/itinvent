import React from 'react';
import {
  Card,
  CardContent,
  Chip,
  Grid,
  IconButton,
  Stack,
  Typography,
  Box,
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';

export default function BranchList({
  branches,
  canEdit,
  onBranchClick,
  onEditClick,
  onDeleteClick,
}) {
  if (!branches || branches.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Филиалы не найдены.
      </Typography>
    );
  }

  return (
    <Grid container spacing={1.5}>
      {branches.map((branch) => (
        <Grid item xs={12} md={6} lg={4} key={branch.id}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                <Box sx={{ flex: 1, cursor: 'pointer' }} onClick={() => onBranchClick(branch)}>
                  <Typography variant="h6">{branch.name}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {branch.branch_code}
                  </Typography>
                </Box>
                {canEdit && (
                  <Stack direction="row" spacing={0.5}>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onEditClick) onEditClick(branch);
                      }}
                    >
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (onDeleteClick) onDeleteClick(branch);
                      }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                )}
              </Stack>
              <Stack direction="row" spacing={0.8} useFlexGap flexWrap="wrap">
                <Chip size="small" label={`Устройства: ${branch.devices_count || 0}`} />
                <Chip size="small" label={`Порты: ${branch.ports_count || 0}`} />
                <Chip size="small" label={`Розетки: ${branch.sockets_count || 0}`} />
                <Chip size="small" label={`Карты: ${branch.maps_count || 0}`} />
                <Chip size="small" label={`Точки: ${branch.map_points_count || 0}`} />
              </Stack>
              {branch.default_site_code && (
                <Typography variant="body2" color="primary" sx={{ mt: 1 }}>
                  Код сайта: {branch.default_site_code}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}
