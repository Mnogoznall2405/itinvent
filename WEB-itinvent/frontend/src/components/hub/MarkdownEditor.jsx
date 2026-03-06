import { useMemo, useState } from 'react';
import { Alert, Box, Button, Paper, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import MarkdownRenderer from './MarkdownRenderer';

function MarkdownEditor({
  label = 'Текст',
  value = '',
  onChange,
  minRows = 6,
  placeholder = '',
  enableAiTransform = false,
  transformContext = 'announcement',
  onAiTransform,
}) {
  const [tab, setTab] = useState('edit');
  const [transformLoading, setTransformLoading] = useState(false);
  const [transformError, setTransformError] = useState('');
  const normalizedValue = useMemo(() => String(value || ''), [value]);
  const canTransform = enableAiTransform && typeof onAiTransform === 'function';

  const handleTransform = async () => {
    if (!canTransform || transformLoading) return;
    const sourceText = String(normalizedValue || '').trim();
    if (sourceText.length < 3) return;

    setTransformLoading(true);
    setTransformError('');
    try {
      const response = await onAiTransform(sourceText, transformContext);
      const markdown = String(response?.markdown || response || '').trim();
      if (!markdown) {
        throw new Error('LLM вернул пустой ответ');
      }
      onChange?.(markdown);
      setTab('edit');
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setTransformError(typeof detail === 'string' ? detail : (error?.message || 'Не удалось преобразовать текст'));
    } finally {
      setTransformLoading(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Tabs value={tab} onChange={(_, next) => setTab(next)} sx={{ minHeight: 36 }}>
          <Tab value="edit" label="Редактор" sx={{ minHeight: 36 }} />
          <Tab value="preview" label="Предпросмотр" sx={{ minHeight: 36 }} />
        </Tabs>
        {canTransform ? (
          <Button
            size="small"
            variant="outlined"
            onClick={handleTransform}
            disabled={transformLoading || String(normalizedValue || '').trim().length < 3}
          >
            {transformLoading ? 'Преобразование...' : 'Преобразовать в MD'}
          </Button>
        ) : null}
      </Stack>

      {transformError ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {transformError}
        </Alert>
      ) : null}

      {tab === 'edit' ? (
        <TextField
          label={label}
          value={normalizedValue}
          onChange={(event) => onChange?.(event.target.value)}
          multiline
          minRows={minRows}
          fullWidth
          placeholder={placeholder}
        />
      ) : (
        <Box sx={{ minHeight: 120, p: 1 }}>
          {normalizedValue.trim() ? (
            <MarkdownRenderer value={normalizedValue} />
          ) : (
            <Typography variant="body2" color="text.secondary">
              Нет текста для предпросмотра
            </Typography>
          )}
        </Box>
      )}
    </Paper>
  );
}

export default MarkdownEditor;
