import { Card, Col, Row, Statistic, Table, Tag } from 'antd';
import { ApartmentOutlined, DatabaseOutlined, ExperimentOutlined, FunctionOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { api, type Json } from '../api';
import { useAuth } from '../auth';
import { LatticeSymbol } from '../components/Brand';
import { brand } from '../theme';

export default function HomePage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const nav = useNavigate();
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get('/meta/overview') });
  const stats = useQuery({ queryKey: ['hofstats'], queryFn: () => api.get('/hofs/stats') });
  const jobs = useQuery({ queryKey: ['jobs', 'recent'], queryFn: () => api.get('/jobs', { size: 6 }) });
  const o = ov.data || {};
  const s: Json = stats.data || {};

  const quick = [
    { k: 'qEvaluate', to: '/design/evaluate', icon: <ExperimentOutlined /> },
    { k: 'qGenerate', to: '/design/generate', icon: <FunctionOutlined /> },
    { k: 'qBuild', to: '/builder', icon: <ApartmentOutlined /> },
    { k: 'qDatabase', to: '/database', icon: <DatabaseOutlined /> },
  ];

  const synthonChart = {
    grid: { left: 140, right: 20, top: 10, bottom: 20 },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#EEE9DF' } } },
    yAxis: { type: 'category', inverse: true, data: (s.synthons || []).slice(0, 10).map((x: any[]) => x[0]) },
    series: [{ type: 'bar', data: (s.synthons || []).slice(0, 10).map((x: any[]) => x[1]), itemStyle: { color: brand.gold }, barWidth: 12 }],
  };
  const yearChart = {
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: (s.by_year || []).map((x: any[]) => x[0]) },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#EEE9DF' } } },
    series: [{ type: 'bar', data: (s.by_year || []).map((x: any[]) => x[1]), itemStyle: { color: brand.indigo }, barWidth: '60%' }],
  };

  return (
    <div>
      <div className="hero" style={{ marginBottom: 22 }}>
        <div className="hero-lattice">
          <LatticeSymbol size={360} ink="#F6F4EF" />
        </div>
        <div className="tag">知声无界 · ULTRA-X</div>
        <h1 style={{ marginTop: 10 }}>UltraHOFs</h1>
        <div style={{ fontFamily: 'var(--font-zh)', fontSize: 20, letterSpacing: '0.16em', marginTop: 6, color: '#e8e2d6' }}>{t('brand.tagline')}</div>
        <div style={{ marginTop: 18, color: '#cfc7b8' }}>
          {t('home.welcome')}，{user?.display_name || user?.username}
        </div>
      </div>
      <Row gutter={16} style={{ marginBottom: 18 }}>
        {[
          ['home.entries', o.entries],
          ['home.references', o.references],
          ['home.tectons', o.experimental_tectons],
          ['home.structures', o.structures],
        ].map(([k, v]) => (
          <Col xs={12} md={6} key={k as string}>
            <Card>
              <Statistic title={<span className="zh">{t(k as string)}</span>} value={(v as number) ?? '—'} />
            </Card>
          </Col>
        ))}
      </Row>
      <h2 style={{ margin: '8px 0 12px' }}>{t('home.quick')}</h2>
      <Row gutter={16} style={{ marginBottom: 18 }}>
        {quick.map((q) => (
          <Col xs={24} sm={12} lg={6} key={q.k}>
            <Card hoverable className="mol-card" onClick={() => nav(q.to)} style={{ height: '100%' }}>
              <div style={{ fontSize: 26, color: brand.gold }}>{q.icon}</div>
              <div className="display" style={{ fontSize: 20, marginTop: 6 }}>{t(`home.${q.k}`)}</div>
              <div className="muted" style={{ marginTop: 6 }}>{t(`home.${q.k}Desc`)}</div>
            </Card>
          </Col>
        ))}
      </Row>
      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card title={<span className="display">{t('home.synthons')}</span>}>
            <ReactECharts option={synthonChart} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<span className="display">{t('home.years')}</span>}>
            <ReactECharts option={yearChart} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>
      <Card title={<span className="display">{t('home.recentJobs')}</span>} style={{ marginTop: 16 }} extra={<Link to="/jobs">{t('common.view')}</Link>}>
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={jobs.data?.items || []}
          columns={[
            { title: '#', dataIndex: 'id', width: 70 },
            { title: t('jobs.type'), dataIndex: 'type' },
            { title: t('common.status'), dataIndex: 'status', render: (s: string) => <Tag>{s}</Tag> },
            { title: t('jobs.message'), dataIndex: 'message' },
          ]}
        />
      </Card>
    </div>
  );
}
