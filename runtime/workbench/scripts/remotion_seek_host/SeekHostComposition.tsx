import React, { useEffect, useRef } from 'react';
import {
  AbsoluteFill,
  cancelRender,
  continueRender,
  delayRender,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export type SeekHostProps = {
  entry: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
};

type HostedWindow = Window & {
  __ready?: Promise<unknown>;
  __seek?: (t: number) => unknown;
  __rendererId?: string;
  __requestedStyleId?: string;
  __styleId?: string;
  __score?: { style?: { styleId?: string } };
  __state?: { shot?: string };
};

function postTelemetry(payload: Record<string, unknown>): void {
  void fetch('/__telemetry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {});
}

export const SeekHostComposition: React.FC<SeekHostProps> = ({ entry, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const readyPromiseRef = useRef<Promise<HostedWindow> | null>(null);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    const handle = delayRender(`seek-host-frame-${frame}`);
    let cancelled = false;

    const ensureReady = (): Promise<HostedWindow> => {
      if (readyPromiseRef.current) return readyPromiseRef.current;
      const initPromise = new Promise<HostedWindow>((resolve, reject) => {
        const setupIframe = async () => {
          try {
            const win = iframe.contentWindow as HostedWindow | null;
            const doc = iframe.contentDocument;
            if (!win || !doc) throw new Error('无法访问同源动画页面');
            win.addEventListener('error', (event) => {
              postTelemetry({
                kind: 'error',
                message: event.message || String(event.error || '页面运行错误'),
              });
            });
            win.addEventListener('unhandledrejection', (event) => {
              postTelemetry({
                kind: 'error',
                message: String(event.reason || '未捕获 Promise 拒绝'),
              });
            });
            const style = doc.createElement('style');
            style.textContent = 'button, [role="button"] { visibility: hidden !important; }';
            doc.head?.appendChild(style);
            if (doc.fonts?.ready) await doc.fonts.ready;
            await Promise.all(
              Array.from(doc.images).map((img) =>
                img.complete && img.naturalWidth > 0 ? img.decode().catch(() => {}) : img.decode(),
              ),
            );
            if (win.__ready) await win.__ready;
            if (typeof win.__seek !== 'function') {
              throw new Error('动画必须提供 window.__seek(t)');
            }
            postTelemetry({
              kind: 'runtime',
              renderer_id: win.__rendererId || null,
              requested_style_id: win.__requestedStyleId || win.__score?.style?.styleId || null,
              style_id: win.__styleId || null,
            });
            resolve(win);
          } catch (error) {
            reject(error);
          }
        };

        if (iframe.contentDocument?.readyState === 'complete' && iframe.getAttribute('data-loaded') === '1') {
          void setupIframe();
          return;
        }
        iframe.addEventListener(
          'load',
          () => {
            iframe.setAttribute('data-loaded', '1');
            void setupIframe();
          },
          { once: true },
        );
        iframe.addEventListener(
          'error',
          () => reject(new Error(`加载动画入口失败: ${entry}`)),
          { once: true },
        );
        iframe.src = `/__project/${entry.replace(/^\/+/, '')}`;
      });
      readyPromiseRef.current = initPromise;
      return initPromise;
    };

    ensureReady()
      .then(async (win) => {
        if (cancelled) return;
        const time = frame / fps;
        await win.__seek!(time);
        postTelemetry({
          kind: 'frame',
          frame,
          time,
          shot: win.__state?.shot || null,
          renderer_id: win.__rendererId || null,
          style_id: win.__styleId || null,
        });
        continueRender(handle);
      })
      .catch((error) => {
        if (!cancelled) {
          postTelemetry({ kind: 'error', message: error instanceof Error ? error.message : String(error) });
          cancelRender(error);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [entry, frame, fps]);

  return (
    <AbsoluteFill style={{ margin: 0, padding: 0, overflow: 'hidden', backgroundColor: '#ffffff' }}>
      <iframe
        ref={iframeRef}
        title="med-autocast-seek-host"
        style={{
          width,
          height,
          border: 'none',
          display: 'block',
          overflow: 'hidden',
        }}
      />
    </AbsoluteFill>
  );
};
