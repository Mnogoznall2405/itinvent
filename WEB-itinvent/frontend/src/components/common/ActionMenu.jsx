import { useState, useCallback, memo } from 'react';
import { IconButton, Menu, MenuItem, ListItemIcon, ListItemText, Divider } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import PrintIcon from '@mui/icons-material/Print';
import BatteryChargingFullIcon from '@mui/icons-material/BatteryChargingFull';
import CleaningServicesIcon from '@mui/icons-material/CleaningServices';
import BuildIcon from '@mui/icons-material/Build';

/**
 * Action menu component for table rows
 *
 * Props:
 * - onAction: Callback when action is selected (actionType, item)
 * - actions: Array of actions to show ['view', 'transfer', 'cartridge', 'battery', 'component', 'cleaning']
 * - item: The data item (optional, passed to onAction)
 * - label: ARIA label for the button
 *
 * Actions:
 * - view: Open detail modal
 * - transfer: Transfer equipment
 * - cartridge: Replace cartridge
 * - battery: Replace battery
 * - component: Replace printer component
 * - cleaning: PC cleaning
 */
function ActionMenu({ onAction, actions = ['view'], item = null, label = 'Действия' }) {
  const [anchor, setAnchor] = useState(null);
  const open = Boolean(anchor);

  const handleOpen = useCallback((event) => {
    event.stopPropagation();
    setAnchor(event.currentTarget);
  }, []);

  const handleClose = useCallback(() => {
    setAnchor(null);
  }, []);

  const handleAction = useCallback((actionType) => {
    handleClose();
    onAction(actionType, item);
  }, [onAction, item, handleClose]);

  return (
    <>
      <IconButton
        onClick={handleOpen}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="true"
        size="small"
        sx={{
          width: 44,
          height: 44,
          '@media (min-width: 600px)': {
            width: 36,
            height: 36,
          },
        }}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu
        anchorEl={anchor}
        open={open}
        onClose={handleClose}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        slotProps={{
          paper: {
            sx: {
              minWidth: 200,
              backgroundImage: 'none',
            },
          },
        }}
      >
        {actions.includes('view') && (
          <MenuItem onClick={() => handleAction('view')}>
            <ListItemIcon>
              <SwapHorizIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Просмотр</ListItemText>
          </MenuItem>
        )}
        {actions.includes('transfer') && (
          <MenuItem onClick={() => handleAction('transfer')}>
            <ListItemIcon>
              <SwapHorizIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Переместить</ListItemText>
          </MenuItem>
        )}
        {(actions.includes('view') || actions.includes('transfer')) &&
         (actions.includes('cartridge') || actions.includes('battery') || actions.includes('component') || actions.includes('cleaning')) && (
          <Divider />
        )}
        {actions.includes('cartridge') && (
          <MenuItem onClick={() => handleAction('cartridge')}>
            <ListItemIcon>
              <PrintIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Замена картриджа</ListItemText>
          </MenuItem>
        )}
        {actions.includes('battery') && (
          <MenuItem onClick={() => handleAction('battery')}>
            <ListItemIcon>
              <BatteryChargingFullIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Замена батареи</ListItemText>
          </MenuItem>
        )}
        {actions.includes('component') && (
          <MenuItem onClick={() => handleAction('component')}>
            <ListItemIcon>
              <BuildIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Замена компонента</ListItemText>
          </MenuItem>
        )}
        {actions.includes('cleaning') && (
          <MenuItem onClick={() => handleAction('cleaning')}>
            <ListItemIcon>
              <CleaningServicesIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText>Чистка ПК</ListItemText>
          </MenuItem>
        )}
      </Menu>
    </>
  );
}

export default memo(ActionMenu);
