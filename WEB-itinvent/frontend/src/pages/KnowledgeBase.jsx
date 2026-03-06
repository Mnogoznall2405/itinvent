import { useMemo } from 'react';
import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import MainLayout from '../components/layout/MainLayout';

const WIKI_URL = 'https://wiki.zsgp.ru/';

function KnowledgeBase() {
  const wikiHost = useMemo(() => {
    try {
      return new URL(WIKI_URL).host;
    } catch {
      return WIKI_URL;
    }
  }, []);

  const openInNewTab = () => {
    window.open(WIKI_URL, '_blank', 'noopener,noreferrer');
  };

  return (
    <MainLayout>
      <Stack spacing={2} sx={{ height: 'calc(100vh - 120px)' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
          <Box>
            <Typography variant="h4">IT База знаний</Typography>
            <Typography variant="body2" color="text.secondary">
              Встроенный портал знаний: {wikiHost}
            </Typography>
          </Box>
          <Button variant="contained" startIcon={<OpenInNewIcon />} onClick={openInNewTab}>
            Открыть в новой вкладке
          </Button>
        </Stack>

        <Alert severity="info">
          Если страница не отображается внутри портала, откройте wiki кнопкой выше. Это зависит от настроек безопасности сайта wiki.
        </Alert>

        <Paper variant="outlined" sx={{ flex: 1, overflow: 'hidden' }}>
          <Box
            component="iframe"
            src={WIKI_URL}
            title="IT Wiki"
            sx={{ width: '100%', height: '100%', border: 0, display: 'block' }}
          />
        </Paper>
      </Stack>
    </MainLayout>
  );
}

export default KnowledgeBase;
