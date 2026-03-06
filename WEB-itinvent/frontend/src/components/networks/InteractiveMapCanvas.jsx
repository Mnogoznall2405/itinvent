import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, IconButton, Stack, Tooltip, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import RestartAltIcon from '@mui/icons-material/RestartAlt';

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const midpoint = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

function InteractiveMapCanvas({
  imageUrl,
  points,
  selectedPointId,
  focusPointId,
  onPointSelect,
  onPointDrop,
  onCanvasClick,
  disabled = false,
  mobile = false,
  height = { xs: 460, md: 760, lg: 820 },
}) {
  const containerRef = useRef(null);
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });
  const [baseSize, setBaseSize] = useState({ width: 0, height: 0 });
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [draggedPoint, setDraggedPoint] = useState(null);
  const isPointPointerDownRef = useRef(false);
  const dragRef = useRef({ startX: 0, startY: 0, offsetX: 0, offsetY: 0, moved: false });
  const pointDragRef = useRef({ active: false, pointId: null, pointerId: null, moved: false });
  const activePointersRef = useRef(new Map());
  const pinchRef = useRef({
    active: false,
    startDistance: 0,
    startScale: 1,
    worldX: 0,
    worldY: 0,
  });

  const ratio = useMemo(() => {
    if (!naturalSize.width || !naturalSize.height) {
      return 1;
    }
    return naturalSize.height / naturalSize.width;
  }, [naturalSize.height, naturalSize.width]);

  // Группировка точек, находящихся близко друг к другу
  const CLUSTER_THRESHOLD = 0.015; // порог срабатывания (примерно 1.5% размера карты)
  const clusteredPoints = useMemo(() => {
    if (!points || !points.length) return [];

    // Если точка перетаскивается, она всегда сама по себе и использует displayXRatio/displayYRatio
    const clusters = [];

    points.forEach((p) => {
      // Проверяем, перетаскивается ли точка индивидуально (не должно быть для кластеров, но на всякий)
      const isIndividuallyDragged = draggedPoint && draggedPoint.id === p.id;
      // Проверяем, перетаскивается ли весь кластер, где сидит эта точка
      const isDraggingCluster = draggedPoint && draggedPoint.clusterId && draggedPoint.ids?.includes(p.id);

      const isBeingDragged = isIndividuallyDragged || isDraggingCluster;

      let x = Number(p.x_ratio || 0);
      let y = Number(p.y_ratio || 0);

      if (isIndividuallyDragged || isDraggingCluster) {
        x = draggedPoint.xRatio;
        y = draggedPoint.yRatio;
      }

      const pWithCoords = { ...p, displayXRatio: x, displayYRatio: y, isBeingDragged };

      let foundCluster = false;
      // Ищем подходящий кластер, если точка не перетаскивается индивидуально
      if (!isIndividuallyDragged) {
        for (let i = 0; i < clusters.length; i++) {
          const c = clusters[i];
          // Если в кластере есть индивидуально перетаскиваемая точка, не объединяемся с ним
          if (c.points.some(cp => cp.isBeingDragged && !draggedPoint?.clusterId)) continue;

          const dx = c.centerX - x;
          const dy = c.centerY - y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < CLUSTER_THRESHOLD) {
            c.points.push(pWithCoords);
            // Пересчитываем центр масс
            c.centerX = c.points.reduce((sum, curr) => sum + curr.displayXRatio, 0) / c.points.length;
            c.centerY = c.points.reduce((sum, curr) => sum + curr.displayYRatio, 0) / c.points.length;
            foundCluster = true;
            break;
          }
        }
      }

      if (!foundCluster) {
        clusters.push({
          id: `cluster_${p.id}`,
          points: [pWithCoords],
          centerX: x,
          centerY: y
        });
      }
    });

    return clusters;
  }, [points, draggedPoint]);

  const recalcBaseSize = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const width = container.clientWidth;
    if (!width) return;
    setBaseSize({
      width,
      height: Math.max(240, Math.round(width * ratio)),
    });
  }, [ratio]);

  useEffect(() => {
    recalcBaseSize();
  }, [recalcBaseSize]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const resizeObserver = new ResizeObserver(() => recalcBaseSize());
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [recalcBaseSize]);

  useEffect(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    activePointersRef.current.clear();
    pinchRef.current.active = false;
  }, [imageUrl]);

  const centerOnPoint = useCallback(
    (pointId) => {
      if (!pointId) return;
      const point = (points || []).find((item) => Number(item.id) === Number(pointId));
      const container = containerRef.current;
      if (!point || !container || !baseSize.width || !baseSize.height) return;
      const targetX = Number(point.x_ratio || 0) * baseSize.width;
      const targetY = Number(point.y_ratio || 0) * baseSize.height;
      const cx = container.clientWidth / 2;
      const cy = container.clientHeight / 2;
      setOffset({ x: cx - targetX * scale, y: cy - targetY * scale });
    },
    [baseSize.height, baseSize.width, points, scale]
  );

  useEffect(() => {
    if (focusPointId) {
      centerOnPoint(focusPointId);
    }
  }, [centerOnPoint, focusPointId]);

  const zoomBy = useCallback((delta, origin = null) => {
    const container = containerRef.current;
    if (!container) return;
    const nextScale = clamp(scale + delta, 0.6, 3);
    if (nextScale === scale) return;

    if (!origin) {
      setScale(nextScale);
      return;
    }

    const rect = container.getBoundingClientRect();
    const ox = origin.x - rect.left;
    const oy = origin.y - rect.top;
    setOffset((prev) => {
      const worldX = (ox - prev.x) / scale;
      const worldY = (oy - prev.y) / scale;
      return {
        x: ox - worldX * nextScale,
        y: oy - worldY * nextScale,
      };
    });
    setScale(nextScale);
  }, [scale]);

  const handleWheel = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    const delta = event.deltaY < 0 ? 0.1 : -0.1;
    zoomBy(delta, { x: event.clientX, y: event.clientY });
  }, [zoomBy]);

  useEffect(() => {
    const globalWheelHandler = (event) => {
      const container = containerRef.current;
      if (!container) return;
      const targetNode = event.target;
      if (!(targetNode instanceof Node)) return;
      if (!container.contains(targetNode)) return;
      handleWheel(event);
    };
    window.addEventListener('wheel', globalWheelHandler, { passive: false, capture: true });
    return () => window.removeEventListener('wheel', globalWheelHandler, true);
  }, [handleWheel]);

  const handlePointerDown = (event) => {
    if (disabled) return;
    if (event.target?.closest?.('[data-map-point="1"]') || isPointPointerDownRef.current) {
      return;
    }
    activePointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });

    const pointers = Array.from(activePointersRef.current.values());
    if (pointers.length >= 2) {
      const [p1, p2] = pointers;
      const mid = midpoint(p1, p2);
      const startDist = distance(p1, p2);
      pinchRef.current = {
        active: true,
        startDistance: Math.max(1, startDist),
        startScale: scale,
        worldX: (mid.x - (containerRef.current?.getBoundingClientRect().left || 0) - offset.x) / scale,
        worldY: (mid.y - (containerRef.current?.getBoundingClientRect().top || 0) - offset.y) / scale,
      };
      setIsDragging(false);
      dragRef.current.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      return;
    }

    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
      moved: false,
    };
    setIsDragging(true);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const handlePointerMove = (event) => {
    if (activePointersRef.current.has(event.pointerId)) {
      activePointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    }

    if (pinchRef.current.active) {
      const pointers = Array.from(activePointersRef.current.values());
      if (pointers.length >= 2) {
        const [p1, p2] = pointers;
        const mid = midpoint(p1, p2);
        const currentDistance = Math.max(1, distance(p1, p2));
        const nextScale = clamp(
          pinchRef.current.startScale * (currentDistance / pinchRef.current.startDistance),
          0.6,
          3
        );
        const rect = containerRef.current?.getBoundingClientRect();
        const ox = mid.x - (rect?.left || 0);
        const oy = mid.y - (rect?.top || 0);
        setOffset({
          x: ox - pinchRef.current.worldX * nextScale,
          y: oy - pinchRef.current.worldY * nextScale,
        });
        setScale(nextScale);
        dragRef.current.moved = true;
      }
      return;
    }

    if (!isDragging) return;
    const dx = event.clientX - dragRef.current.startX;
    const dy = event.clientY - dragRef.current.startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      dragRef.current.moved = true;
    }
    setOffset({
      x: dragRef.current.offsetX + dx,
      y: dragRef.current.offsetY + dy,
    });
  };

  const handlePointerUp = (event) => {
    activePointersRef.current.delete(event.pointerId);

    if (pinchRef.current.active) {
      const remainingPointers = Array.from(activePointersRef.current.values());
      if (remainingPointers.length < 2) {
        pinchRef.current.active = false;
      }
      if (remainingPointers.length === 1) {
        const [p] = remainingPointers;
        dragRef.current = {
          startX: p.x,
          startY: p.y,
          offsetX: offset.x,
          offsetY: offset.y,
          moved: true,
        };
        setIsDragging(true);
      } else {
        setIsDragging(false);
      }
    } else {
      setIsDragging(false);
    }

    if (activePointersRef.current.size === 0) {
      isPointPointerDownRef.current = false;
    }
  };

  const handleCanvasClick = (event) => {
    if (!onCanvasClick || disabled) return;
    if (dragRef.current.moved) {
      dragRef.current.moved = false;
      return;
    }
    const target = event.target;
    if (target.closest('[data-map-point="1"]')) {
      return;
    }
    const container = containerRef.current;
    if (!container || !baseSize.width || !baseSize.height) return;

    const rect = container.getBoundingClientRect();
    const x = (event.clientX - rect.left - offset.x) / scale;
    const y = (event.clientY - rect.top - offset.y) / scale;
    const xRatio = clamp(x / baseSize.width, 0, 1);
    const yRatio = clamp(y / baseSize.height, 0, 1);
    onCanvasClick({ xRatio, yRatio });
  };

  const buildPointTooltip = useCallback((point) => {
    const socket = String(point?.patch_panel_port || '').trim();
    const port = String(point?.port_name || '').trim();
    const device = String(point?.device_code || '').trim();
    const ip = String(point?.endpoint_ip_raw || '').trim();
    const fio = String(point?.fio || '').trim();
    const label = String(point?.label || '').trim();
    const lines = [];
    if (socket) lines.push(`🔌 Розетка: ${socket}`);
    if (port && device) lines.push(`📡 ${device} · ${port}`);
    else if (port) lines.push(`📡 PORT: ${port}`);
    else if (device) lines.push(`📡 ${device}`);
    if (ip) lines.push(`🌐 ${ip}`);
    if (fio) lines.push(`👤 ${fio}`);
    if (label) lines.push(label);
    return lines.length > 0 ? lines.join('\n') : `Точка #${point?.id || ''}`;
  }, []);

  const getPointLabel = useCallback((point) => {
    const socket = String(point?.patch_panel_port || '').trim();
    if (socket) return socket;
    const port = String(point?.port_name || '').trim();
    if (port) return port;
    return String(point?.label || '').trim() || '';
  }, []);

  /* ─── Pin SVG marker ─── */
  const PinMarker = useCallback(({ color = '#1976d2', size = 28, selected = false, focused = false }) => (
    <svg
      width={size}
      height={Math.round(size * 1.35)}
      viewBox="0 0 24 33"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: 'block', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.35))' }}
    >
      <defs>
        <linearGradient id={`pin-grad-${color.replace('#', '')}`} x1="12" y1="0" x2="12" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor={color} stopOpacity="1" />
          <stop offset="100%" stopColor={color} stopOpacity="0.7" />
        </linearGradient>
      </defs>
      <path
        d="M12 0C5.373 0 0 5.373 0 12c0 8.25 10.5 19.5 11.25 20.25.375.375 1.125.375 1.5 0C13.5 31.5 24 20.25 24 12c0-6.627-5.373-12-12-12z"
        fill={`url(#pin-grad-${color.replace('#', '')})`}
        stroke="white"
        strokeWidth={selected ? 2.5 : 1.5}
      />
      <circle cx="12" cy="12" r="5" fill="white" fillOpacity="0.9" />
      {(selected || focused) && (
        <circle cx="12" cy="12" r="5" fill="none" stroke="white" strokeWidth="1.5" opacity="0.6">
          <animate attributeName="r" values="5;9;5" dur="1.5s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.6;0;0.6" dur="1.5s" repeatCount="indefinite" />
        </circle>
      )}
    </svg>
  ), []);

  return (
    <Box sx={{ position: 'relative' }}>
      {/* ─── Zoom controls ─── */}
      <Stack
        direction="row"
        spacing={0.5}
        sx={{
          position: 'absolute',
          right: 8,
          top: 8,
          zIndex: 3,
          bgcolor: 'rgba(0,0,0,0.55)',
          borderRadius: 2,
          p: 0.3,
          backdropFilter: 'blur(6px)',
        }}
      >
        <Tooltip title="Увеличить">
          <IconButton size="small" sx={{ color: 'white' }} onClick={() => zoomBy(0.1)}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Уменьшить">
          <IconButton size="small" sx={{ color: 'white' }} onClick={() => zoomBy(-0.1)}>
            <RemoveIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Сбросить">
          <IconButton
            size="small"
            sx={{ color: 'white' }}
            onClick={() => {
              setScale(1);
              setOffset({ x: 0, y: 0 });
            }}
          >
            <RestartAltIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      <Box
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onClick={handleCanvasClick}
        sx={{
          width: '100%',
          minHeight: 420,
          height,
          overflow: 'hidden',
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          position: 'relative',
          bgcolor: 'grey.100',
          cursor: isDragging ? 'grabbing' : 'grab',
          userSelect: 'none',
          touchAction: 'none',
          overscrollBehavior: 'contain',
        }}
      >
        {imageUrl ? (
          <Box
            sx={{
              position: 'absolute',
              left: 0,
              top: 0,
              width: `${baseSize.width}px`,
              height: `${baseSize.height}px`,
              transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
              transformOrigin: 'top left',
              transition: isDragging ? 'none' : 'transform 0.35s cubic-bezier(0.2, 0, 0, 1)',
            }}
          >
            <img
              src={imageUrl}
              alt="Карта филиала"
              draggable={false}
              onLoad={(event) => {
                const target = event.currentTarget;
                setNaturalSize({ width: target.naturalWidth, height: target.naturalHeight });
              }}
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', pointerEvents: 'none' }}
            />

            {clusteredPoints.map((cluster) => {
              // Если в кластере только одна точка
              if (cluster.points.length === 1) {
                const point = cluster.points[0];
                const pointId = Number(point.id || 0);
                const isSelected = pointId === Number(selectedPointId);
                const isFocused = pointId === Number(focusPointId);
                const isBeingDragged = point.isBeingDragged;
                const displayXRatio = point.displayXRatio;
                const displayYRatio = point.displayYRatio;

                // 1. Уменьшаем размеры маркеров
                const pinSize = mobile ? (isSelected ? 16 : 12) : (isSelected ? 24 : 16);

                // 2. Логика цвета
                const isSocket = !!point.patch_panel_port;
                const isConnected = !!(point.port_name || point.device_code);
                const isEmptySocket = isSocket && !isConnected;

                let baseColor = '#1976d2';
                if (isEmptySocket) baseColor = '#757575';

                const pinColor = point.color || (isSelected ? '#ed6c02' : baseColor);
                const label = getPointLabel(point);
                return (
                  <Box key={cluster.id}>
                    <Tooltip
                      title={
                        <Typography variant="caption" component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', m: 0, lineHeight: 1.5, fontSize: '0.78rem' }}>
                          {buildPointTooltip(point)}
                        </Typography>
                      }
                      arrow
                      placement="top"
                      enterDelay={200}
                      leaveDelay={100}
                    >
                      <Box
                        data-map-point="1"
                        onPointerDown={(event) => {
                          isPointPointerDownRef.current = true;
                          if (disabled) return;
                          event.stopPropagation();
                          pointDragRef.current = {
                            active: true,
                            pointId: pointId,
                            pointerId: event.pointerId,
                            moved: false,
                          };
                          event.currentTarget.setPointerCapture(event.pointerId);
                        }}
                        onPointerMove={(event) => {
                          if (!pointDragRef.current.active || pointDragRef.current.pointerId !== event.pointerId) return;
                          pointDragRef.current.moved = true;
                          const container = containerRef.current;
                          if (!container || !baseSize.width || !baseSize.height) return;
                          const rect = container.getBoundingClientRect();
                          const x = (event.clientX - rect.left - offset.x) / scale;
                          const y = (event.clientY - rect.top - offset.y) / scale;
                          setDraggedPoint({
                            id: pointId,
                            xRatio: clamp(x / baseSize.width, 0, 1),
                            yRatio: clamp(y / baseSize.height, 0, 1)
                          });
                        }}
                        onPointerUp={(event) => {
                          if (!pointDragRef.current.active || pointDragRef.current.pointerId !== event.pointerId) return;
                          event.stopPropagation();
                          pointDragRef.current.active = false;
                          if (event.currentTarget.releasePointerCapture) {
                            try { event.currentTarget.releasePointerCapture(event.pointerId); } catch (e) { }
                          }

                          // Если мы передвигали маркер
                          if (pointDragRef.current.moved && draggedPoint) {
                            onPointDrop?.(pointId, draggedPoint.xRatio, draggedPoint.yRatio);
                          } else {
                            // Просто клик
                            onPointSelect?.(point);
                          }
                          setDraggedPoint(null);
                        }}
                        onClick={(event) => {
                          event.stopPropagation();
                          // Если был drag, не обрабатываем клик
                        }}
                        sx={{
                          position: 'absolute',
                          left: `${displayXRatio * 100}%`,
                          top: `${displayYRatio * 100}%`,
                          transform: 'translate(-50%, -100%)',
                          zIndex: isSelected ? 5 : isFocused ? 4 : 3,
                          cursor: isBeingDragged ? 'grabbing' : 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          transition: isBeingDragged ? 'none' : 'transform 0.15s ease',
                          '&:hover': { transform: isBeingDragged ? 'translate(-50%, -100%)' : 'translate(-50%, -100%) scale(1.15)', zIndex: 6 },
                        }}
                      >
                        <PinMarker color={pinColor} size={pinSize} selected={isSelected} focused={isFocused} />
                        {label && !mobile && (
                          <Typography
                            variant="caption"
                            sx={{
                              mt: '-2px',
                              px: 0.5,
                              py: 0,
                              fontSize: isSelected ? '0.65rem' : '0.58rem',
                              fontWeight: 700,
                              bgcolor: 'rgba(0,0,0,0.65)',
                              color: 'white',
                              borderRadius: 0.5,
                              lineHeight: 1.3,
                              whiteSpace: 'nowrap',
                              pointerEvents: 'none',
                            }}
                          >
                            {label}
                          </Typography>
                        )}
                      </Box>
                    </Tooltip>
                  </Box>
                );
              } else {
                // Если это кластер из нескольких точек
                const isSelected = cluster.points.some(p => Number(p.id) === Number(selectedPointId));
                const isFocused = cluster.points.some(p => Number(p.id) === Number(focusPointId));
                const clusterBeingDragged = draggedPoint && draggedPoint.clusterId === cluster.id;

                // Текст кластера: разбиваем на массив строк для вывода в столбик
                const clusterTextLines = cluster.points
                  .map(p => p.patch_panel_port ? p.patch_panel_port : (p.device_code || String(p.id)));

                // Удаляем логику фона-градиента, фон будет белой плашкой с рамкой
                const getPointColor = (p) => {
                  const pointId = Number(p.id || 0);
                  if (pointId === Number(selectedPointId)) return '#ed6c02'; // orange (selected)

                  const isSocket = !!p.patch_panel_port;
                  const isConnected = !!(p.port_name || p.device_code);
                  return (isSocket && !isConnected) ? '#757575' : '#1976d2'; // grey for empty, blue for connected
                };

                // Генерируем Tooltip для всех точек в кластере
                const clusterTooltip = cluster.points.map(p => buildPointTooltip(p)).join('\n\n---\n\n');
                const lastPoint = cluster.points[cluster.points.length - 1]; // Для клика берем одну из точек

                return (
                  <Box key={cluster.id}>
                    <Tooltip
                      title={
                        <Typography variant="caption" component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', m: 0, lineHeight: 1.5, fontSize: '0.78rem' }}>
                          {clusterTooltip}
                        </Typography>
                      }
                      arrow
                      placement="top"
                      enterDelay={200}
                      leaveDelay={100}
                    >
                      <Box
                        onPointerDown={(event) => {
                          isPointPointerDownRef.current = true;
                          if (disabled) return;
                          event.stopPropagation();
                          pointDragRef.current = {
                            active: true,
                            pointId: null, // не одна точка
                            clusterId: cluster.id,
                            ids: cluster.points.map(p => p.id), // сохраняем все ID кластера
                            pointerId: event.pointerId,
                            moved: false,
                          };
                          event.currentTarget.setPointerCapture(event.pointerId);
                        }}
                        onPointerMove={(event) => {
                          if (!pointDragRef.current.active || pointDragRef.current.pointerId !== event.pointerId) return;
                          pointDragRef.current.moved = true;
                          const container = containerRef.current;
                          if (!container || !baseSize.width || !baseSize.height) return;
                          const rect = container.getBoundingClientRect();
                          const x = (event.clientX - rect.left - offset.x) / scale;
                          const y = (event.clientY - rect.top - offset.y) / scale;
                          setDraggedPoint({
                            clusterId: cluster.id,
                            ids: cluster.points.map(p => p.id),
                            xRatio: clamp(x / baseSize.width, 0, 1),
                            yRatio: clamp(y / baseSize.height, 0, 1)
                          });
                        }}
                        onPointerUp={(event) => {
                          if (!pointDragRef.current.active || pointDragRef.current.pointerId !== event.pointerId) return;
                          event.stopPropagation();
                          pointDragRef.current.active = false;
                          if (event.currentTarget.releasePointerCapture) {
                            try { event.currentTarget.releasePointerCapture(event.pointerId); } catch (e) { }
                          }

                          if (pointDragRef.current.moved && draggedPoint && draggedPoint.clusterId === cluster.id) {
                            // Отправляем массив ID на бэкенд для обновления всех сразу
                            onPointDrop?.(draggedPoint.ids, draggedPoint.xRatio, draggedPoint.yRatio);
                          } else {
                            onPointSelect?.(lastPoint);
                          }
                          setDraggedPoint(null);
                        }}
                        onClick={(event) => {
                          event.stopPropagation();
                        }}
                        sx={{
                          position: 'absolute',
                          left: `${cluster.centerX * 100}%`,
                          top: `${cluster.centerY * 100}%`,
                          transform: 'translate(-50%, -50%)', // Центруем кружок
                          zIndex: isSelected ? 5 : isFocused ? 4 : 3,
                          cursor: clusterBeingDragged ? 'grabbing' : 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minWidth: mobile ? 20 : 28,
                          height: 'auto',
                          padding: '3px 6px',
                          borderRadius: '8px',
                          bgcolor: 'white',
                          color: '#333',
                          fontWeight: 'bold',
                          fontSize: mobile ? '0.6rem' : '0.68rem',
                          lineHeight: 1.15,
                          boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
                          border: (isSelected || isFocused) ? '2px solid #ed6c02' : '2px solid #ccc',
                          transition: 'transform 0.15s ease',
                          '&:hover': { transform: 'translate(-50%, -50%) scale(1.15)', zIndex: 6 },
                          ...((isSelected || isFocused) && {
                            animation: 'pulse 1.5s infinite',
                            '@keyframes pulse': {
                              '0%': { boxShadow: '0 0 0 0 rgba(237, 108, 2, 0.7)' },
                              '70%': { boxShadow: '0 0 0 10px rgba(237, 108, 2, 0)' },
                              '100%': { boxShadow: '0 0 0 0 rgba(237, 108, 2, 0)' },
                            }
                          })
                        }}
                      >
                        {cluster.points.map((p, idx) => {
                          const text = p.patch_panel_port ? p.patch_panel_port : (p.device_code || String(p.id));
                          return (
                            <div key={idx} style={{ whiteSpace: 'nowrap', color: getPointColor(p) }}>{text}</div>
                          );
                        })}
                      </Box>
                    </Tooltip>
                  </Box>
                );
              }
            })}
          </Box>
        ) : (
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Выберите карту, чтобы начать работу.
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

export default InteractiveMapCanvas;
