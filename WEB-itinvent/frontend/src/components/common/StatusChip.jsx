import { Chip, alpha } from '@mui/material';

/**
 * Status chip component for equipment status display
 *
 * Props:
 * - status: Status text to display
 * - variant: 'filled' | 'outlined'
 * - size: 'small' | 'medium'
 *
 * Status color mapping:
 * - Working/Active → Green
 * - Broken/Inactive → Red
 * - In Repair → Orange
 * - Reserved → Blue
 * - Unknown → Gray
 */
function StatusChip({ status, variant = 'outlined', size = 'small', sx = {} }) {
  // Normalize status for comparison
  const statusLower = (status || '').toLowerCase().trim();

  // Determine color based on status
  const getStatusColor = () => {
    // Working/Active statuses
    if (statusLower.match(/^(работает|active|working|в работе|in use|доступен|available|on|enabled)$/)) {
      return 'success';
    }

    // Broken/Error statuses
    if (statusLower.match(/^(сломан|broken|inactive|error|не работает|not working|failed|ошибк|defect|битый)$/)) {
      return 'error';
    }

    // Repair/Warning statuses
    if (statusLower.match(/^(ремонт|repair|in repair|на ремонте|pending|waiting|ожидание|maintenance|тест|test)$/)) {
      return 'warning';
    }

    // Reserved/Assigned statuses
    if (statusLower.match(/^(занят|reserved|assigned|зарезервирован|выдelan|allocated)$/)) {
      return 'primary';
    }

    // Default/unknown
    return 'default';
  };

  const color = getStatusColor();

  return (
    <Chip
      label={status || '-'}
      size={size}
      variant={variant}
      sx={{
        fontWeight: 500,
        ...(color === 'success' && {
          backgroundColor: variant === 'filled' ? 'success.main' : alpha('#2e7d32', 0.1),
          color: variant === 'filled' ? 'success.contrastText' : 'success.dark',
        }),
        ...(color === 'error' && {
          backgroundColor: variant === 'filled' ? 'error.main' : alpha('#d32f2f', 0.1),
          color: variant === 'filled' ? 'error.contrastText' : 'error.dark',
        }),
        ...(color === 'warning' && {
          backgroundColor: variant === 'filled' ? 'warning.main' : alpha('#ed6c02', 0.1),
          color: variant === 'filled' ? 'warning.contrastText' : 'warning.dark',
        }),
        ...(color === 'primary' && {
          backgroundColor: variant === 'filled' ? 'primary.main' : alpha('#1976d2', 0.1),
          color: variant === 'filled' ? 'primary.contrastText' : 'primary.dark',
        }),
        ...(color === 'default' && {
          backgroundColor: variant === 'filled' ? 'text.primary' : alpha('rgba(0, 0, 0, 0.87)', 0.1),
          color: variant === 'filled' ? 'primary.contrastText' : 'text.primary',
        }),
        ...sx,
      }}
    />
  );
}

export default StatusChip;
