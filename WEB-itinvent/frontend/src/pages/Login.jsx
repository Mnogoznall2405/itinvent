/**
 * Login page - authenticate users.
 */
import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { LockOutlined, Visibility, VisibilityOff } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';

function Login() {
  const { login } = useAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const isSubmitDisabled = useMemo(
    () => loading || !username.trim() || !password.trim(),
    [loading, username, password]
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);
    setLoading(true);

    const result = await login(username.trim(), password);
    setLoading(false);

    if (result.success) {
      window.location.assign('https://hubit.zsgp.ru/dashboard');
      return;
    }
    setError(result.error);
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        background:
          'radial-gradient(circle at 20% 20%, rgba(25,118,210,0.15), transparent 40%), radial-gradient(circle at 80% 0%, rgba(0,121,107,0.12), transparent 35%)',
      }}
    >
      <Container maxWidth="sm">
        <Card sx={{ borderRadius: 3, boxShadow: 6 }}>
          <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
            <Stack spacing={2} alignItems="center" sx={{ mb: 3 }}>
              <Box
                sx={{
                  width: 56,
                  height: 56,
                  borderRadius: '50%',
                  display: 'grid',
                  placeItems: 'center',
                  backgroundColor: 'primary.main',
                }}
              >
                <LockOutlined sx={{ color: 'white' }} />
              </Box>
              <Box textAlign="center">
                <Typography component="h1" variant="h5" sx={{ fontWeight: 700 }}>
                  HUB-IT
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Вход в систему
                </Typography>
              </Box>
            </Stack>

            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}

            <Box component="form" onSubmit={handleSubmit}>
              <TextField
                fullWidth
                label="Логин"
                margin="normal"
                required
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                disabled={loading}
              />
              <TextField
                fullWidth
                label="Пароль"
                margin="normal"
                required
                autoComplete="current-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={loading}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        edge="end"
                        onClick={() => setShowPassword((prev) => !prev)}
                        aria-label="toggle password visibility"
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <Button
                fullWidth
                type="submit"
                variant="contained"
                sx={{ mt: 3, py: 1.2, fontWeight: 600 }}
                disabled={isSubmitDisabled}
              >
                {loading ? <CircularProgress size={22} color="inherit" /> : 'Войти'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Container>
    </Box>
  );
}

export default Login;
