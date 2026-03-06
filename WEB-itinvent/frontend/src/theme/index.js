import { createTheme, responsiveFontSizes } from '@mui/material/styles';

/**
 * Design System for IT-invent Web
 *
 * Color Palette:
 * - Primary: Blue (#1976d2) - main brand color
 * - Secondary: Teal (#00796b) - accents
 * - Background: Light gray (#f5f7fa) - app background
 * - Surface: White (#ffffff) - cards, dialogs
 * - Error: Red (#d32f2f) - errors, destructive actions
 * - Warning: Orange (#ed6c02) - warnings
 * - Success: Green (#2e7d32) - success states
 *
 * Typography:
 * - Font: Inter (system font stack)
 * - Scale: 12/14/16/20/24px (mobile adjusted)
 *
 * Spacing:
 * - Base unit: 8px
 * - Components use consistent padding/margins
 *
 * Mobile-first:
 * - All components designed mobile-first
 * - Touch targets: minimum 44x44px
 * - Readable text: minimum 16px body
 */

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#4286f4',
      dark: '#004ba0',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#00796b',
      light: '#33969c',
      dark: '#004c42',
      contrastText: '#ffffff',
    },
    error: {
      main: '#d32f2f',
      light: '#ef5350',
      dark: '#c62828',
      contrastText: '#ffffff',
    },
    warning: {
      main: '#ed6c02',
      light: '#f29c40',
      dark: '#b26a00',
      contrastText: '#ffffff',
    },
    success: {
      main: '#2e7d32',
      light: '#4caf50',
      dark: '#1b5e20',
      contrastText: '#ffffff',
    },
    background: {
      default: '#f5f7fa',
      paper: '#ffffff',
    },
    text: {
      primary: 'rgba(0, 0, 0, 0.87)',
      secondary: 'rgba(0, 0, 0, 0.6)',
      disabled: 'rgba(0, 0, 0, 0.38)',
    },
    divider: 'rgba(0, 0, 0, 0.12)',
    action: {
      active: 'rgba(25, 118, 210, 0.08)',
      hover: 'rgba(25, 118, 210, 0.04)',
      selected: 'rgba(25, 118, 210, 0.12)',
      disabledBackground: 'rgba(0, 0, 0, 0.08)',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
    fontSize: 14, // Base font size
    h1: {
      fontSize: '2rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '2.5rem',
      },
    },
    h2: {
      fontSize: '1.5rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '2rem',
      },
    },
    h3: {
      fontSize: '1.25rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '1.75rem',
      },
    },
    h4: {
      fontSize: '1.125rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '1.5rem',
      },
    },
    h5: {
      fontSize: '1rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '1.25rem',
      },
    },
    h6: {
      fontSize: '0.875rem',
      fontWeight: 600,
      '@media (min-width:600px)': {
        fontSize: '1rem',
      },
    },
    body1: {
      fontSize: '0.875rem', // 14px - good for mobile
      '@media (min-width:600px)': {
        fontSize: '1rem', // 16px - desktop
      },
    },
    body2: {
      fontSize: '0.75rem',
      '@media (min-width:600px)': {
        fontSize: '0.875rem',
      },
    },
    button: {
      textTransform: 'none', // Don't uppercase buttons
      fontWeight: 500,
    },
  },
  spacing: 8, // Base unit
  shape: {
    borderRadius: 8, // Consistent border radius
  },
  shadows: [
    'none',
    '0 2px 4px rgba(0,0,0,0.1)',
    '0 4px 8px rgba(0,0,0,0.1)',
    '0 8px 16px rgba(0,0,0,0.08)',
    '0 12px 24px rgba(0,0,0,0.08)',
    // ... rest of default shadows
  ],
  components: {
    // Paper component (cards, dialogs)
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none', // Better performance
        },
      },
      defaultProps: {
        elevation: 2,
      },
    },
    // Button component
    MuiButton: {
      styleOverrides: {
        root: {
          minWidth: 44, // Touch target size
          minHeight: 44,
          borderRadius: 8,
          textTransform: 'none',
          fontWeight: 500,
          '@media (min-width:600px)': {
            minWidth: 64,
            minHeight: 36,
          },
        },
      },
    },
    // TextField
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'small',
      },
    },
    MuiFilledInput: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(0,0,0,0.03)',
          '&:hover': {
            backgroundColor: 'rgba(0,0,0,0.05)',
          },
          '&.Mui-focused': {
            backgroundColor: 'rgba(0,0,0,0.05)',
          },
        },
      },
    },
    // IconButton - ensure touch targets
    MuiIconButton: {
      styleOverrides: {
        root: {
          width: 44,
          height: 44,
          '@media (min-width:600px)': {
            width: 36,
            height: 36,
          },
        },
      },
    },
    // Table
    MuiTable: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-root': {
            paddingLeft: 12,
            paddingRight: 12,
            '@media (max-width:600px)': {
              paddingLeft: 8,
              paddingRight: 8,
              fontSize: '0.75rem',
              padding: '6px 4px',
            },
          },
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          transition: 'background-color 150ms ease',
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottomColor: 'rgba(0,0,0,0.06)',
        },
        head: {
          fontWeight: 600,
          color: 'rgba(0,0,0,0.6)',
        },
      },
    },
    // Checkbox
    MuiCheckbox: {
      styleOverrides: {
        root: {
          width: 32,
          height: 32,
          '@media (min-width:600px)': {
            width: 24,
            height: 24,
          },
        },
      },
    },
    // Chip
    MuiChip: {
      defaultProps: {
        size: 'small',
      },
    },
    // Dialog
    MuiDialog: {
      styleOverrides: {
        root: {
          '@media (max-width:600px)': {
            '& .MuiDialog-paper': {
              margin: 16,
              maxWidth: 'calc(100% - 32px)',
            },
          },
        },
      },
    },
    // AppBar
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
    // Drawer
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none',
        },
      },
    },
    // Tabs
    MuiTab: {
      styleOverrides: {
        root: {
          minWidth: 72,
          textTransform: 'none',
          fontWeight: 500,
          '@media (max-width:600px)': {
            minWidth: 56,
            fontSize: '0.75rem',
            padding: '8px 12px',
          },
        },
      },
    },
  },
});

export default theme;
