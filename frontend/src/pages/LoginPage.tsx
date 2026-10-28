import { Alert, Button, Form, Input } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { BrandMark, LatticeSymbol } from '../components/Brand';
import { setLanguage } from '../i18n';

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={loc.state?.from || '/'} replace />;
  const points = t('login.points', { returnObjects: true }) as string[];

  const submit = async (v: { username: string; password: string }) => {
    setBusy(true);
    setErr('');
    try {
      await login(v.username, v.password);
      nav(loc.state?.from || '/', { replace: true });
    } catch (e: any) {
      setErr(e.message || t('login.failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-brand">
        <BrandMark size={44} dark />
        <div>
          <div style={{ fontFamily: 'var(--font-zh)', fontSize: 44, letterSpacing: '0.18em', lineHeight: 1.3 }}>知声无界</div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, letterSpacing: '0.42em', color: '#d9c39b', marginTop: 6 }}>ULTRA-X</div>
          <p style={{ marginTop: 34, fontFamily: 'var(--font-zh)', fontSize: 19, maxWidth: 460, lineHeight: 1.8, color: '#e8e2d6' }}>{t('login.lead')}</p>
          <ul style={{ paddingLeft: 18, color: '#cfc7b8', lineHeight: 2 }}>
            {points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
        <div style={{ opacity: 0.35 }}>
          <LatticeSymbol size={90} ink="#F6F4EF" />
        </div>
      </div>
      <div className="login-form">
        <div style={{ width: 360 }}>
          <h1 style={{ fontSize: 34, marginBottom: 4 }}>{t('login.title')}</h1>
          <div className="muted zh" style={{ letterSpacing: '0.12em', marginBottom: 28 }}>
            UltraHOFs · {t('brand.tagline')}
          </div>
          {err ? <Alert type="error" showIcon message={err} style={{ marginBottom: 16 }} /> : null}
          <Form layout="vertical" onFinish={submit} requiredMark={false}>
            <Form.Item name="username" label={t('login.username')} rules={[{ required: true }]}>
              <Input size="large" prefix={<UserOutlined />} autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label={t('login.password')} rules={[{ required: true }]}>
              <Input.Password size="large" prefix={<LockOutlined />} autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" size="large" block loading={busy}>
              {t('login.submit')}
            </Button>
          </Form>
          <Button type="link" style={{ marginTop: 18, padding: 0 }} onClick={() => setLanguage(i18n.language === 'zh-CN' ? 'en-US' : 'zh-CN')}>
            {i18n.language === 'zh-CN' ? 'English' : '中文'}
          </Button>
        </div>
      </div>
    </div>
  );
}
