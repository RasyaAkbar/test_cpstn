import { useEffect, useState } from 'react';
import { apiGet } from '../api/client';
import { Button } from '../ui';

type Health = { status: 'ok' };

export function ServiceStatus() {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    apiGet<Health>('/health', controller.signal)
      .then((result) => { if (active) setStatus(result.status === 'ok' ? 'online' : 'offline'); })
      .catch(() => { if (active) setStatus('offline'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [attempt]);

  return <div className={`service-status ${status}`}>
    <span role="status"><span className="status-dot" />{status === 'checking' ? 'Memeriksa API…' : status === 'online' ? 'API terhubung' : 'API belum terhubung'}</span>
    {status === 'offline' && <Button variant="outline" size="sm" onClick={() => { setStatus('checking'); setAttempt(attempt + 1); }}>Coba lagi</Button>}
  </div>;
}
