import { Button, Dropdown, Layout, Menu, Space, Switch, Typography } from 'antd';
import { GlobalOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { setLanguage } from '../i18n';
import { BrandMark } from './Brand';

const { Header, Content, Footer } = Layout;

export function AppLayout({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation();
  const { user, logout, isCurator } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [fangsong, setFangsong] = useState(localStorage.getItem('uh_body_fangsong') === '1');

  useEffect(() => {
    document.body.classList.toggle('body-fangsong', fangsong);
    localStorage.setItem('uh_body_fangsong', fangsong ? '1' : '0');
  }, [fangsong]);

  const top = '/' + (loc.pathname.split('/')[1] || '');
  const items = [
    { key: '/', label: <Link to="/">{t('nav.home')}</Link> },
    { key: '/database', label: <Link to="/database">{t('nav.database')}</Link> },
    {
      key: '/design',
      label: t('nav.design'),
      children: [
        { key: '/design/evaluate', label: <Link to="/design/evaluate">{t('nav.evaluate')}</Link> },
        { key: '/design/generate', label: <Link to="/design/generate">{t('nav.generate')}</Link> },
        { key: '/design/pairs', label: <Link to="/design/pairs">{t('nav.pairs')}</Link> },
      ],
    },
    { key: '/builder', label: <Link to="/builder">{t('nav.builder')}</Link> },
    { key: '/structures', label: <Link to="/structures">{t('nav.structures')}</Link> },
    { key: '/jobs', label: <Link to="/jobs">{t('nav.jobs')}</Link> },
    { key: '/projects', label: <Link to="/projects">{t('nav.projects')}</Link> },
    ...(isCurator ? [{ key: '/admin', label: <Link to="/admin">{t('nav.admin')}</Link> }] : []),
  ];
  const selected = top === '/design' ? loc.pathname : top;

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: 24, borderBottom: '1px solid var(--line)', position: 'sticky', top: 0, zIndex: 10 }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center' }}>
          <BrandMark size={34} />
        </Link>
        <Menu mode="horizontal" selectedKeys={[selected]} items={items} style={{ flex: 1, minWidth: 0, borderBottom: 'none', fontFamily: 'var(--font-zh)', fontSize: 15 }} />
        <Space size={14}>
          <Button type="text" icon={<GlobalOutlined />} onClick={() => setLanguage(i18n.language === 'zh-CN' ? 'en-US' : 'zh-CN')}>
            {t('nav.lang')}
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'font',
                  label: (
                    <Space onClick={(e) => e.stopPropagation()}>
                      {t('nav.bodyFont')}
                      <Switch size="small" checked={fangsong} onChange={setFangsong} />
                    </Space>
                  ),
                },
                { key: 'about', label: <Link to="/about">{t('nav.about')}</Link> },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: t('nav.logout'), onClick: () => { logout(); nav('/login'); } },
              ],
            }}
          >
            <Button type="text" icon={<UserOutlined />}>
              {user?.display_name || user?.username}
            </Button>
          </Dropdown>
        </Space>
      </Header>
      <Content style={{ padding: '24px 32px 40px', maxWidth: 1480, width: '100%', margin: '0 auto' }}>{children}</Content>
      <Footer style={{ textAlign: 'center', borderTop: '1px solid var(--line)' }}>
        <Typography.Text className="footer-brand muted">{t('footer')}</Typography.Text>
        <span className="muted" style={{ marginLeft: 16, fontSize: 12 }}>
          © 2026 Ultra-X 知声无界 · All rights reserved · <Link to="/about">{t('nav.about')}</Link>
        </span>
      </Footer>
    </Layout>
  );
}
