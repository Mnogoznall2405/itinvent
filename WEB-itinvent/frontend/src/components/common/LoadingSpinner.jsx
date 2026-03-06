import { CircularProgress, Box, Typography } from '@mui/material';

/**
 * Reusable loading spinner with optional message
 *
 * Props:
 * - size: 'small' | 'medium' (default)
 * - message: Optional text to display below spinner
 * - fullScreen: Center in viewport with overlay
 */
function LoadingSpinner({ size = 'medium', message, fullScreen = false }) {
  const content = (
    <>
      <CircularProgress
        size={size === 'small' ? 32 : 48}
        sx={{
          color: 'primary.main',
        }}
      />
      {message && (
        <Typography
          variant="body2"
          sx={{
            mt: 2,
            color: 'text.secondary',
            textAlign: 'center',
          }}
        >
          {message}
        </Typography>
      )}
    </>
  );

  if (fullScreen) {
    return (
      <Box
        sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'rgba(255, 255, 255, 0.9)',
          zIndex: 9999,
        }}
      >
        <Box sx={{ p: 3 }}>
          {content}
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: 3,
      }}
    >
      {content}
    </Box>
  );
}

export default LoadingSpinner;
