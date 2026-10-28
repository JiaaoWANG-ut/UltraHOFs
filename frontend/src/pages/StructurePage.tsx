import { Alert, Button, Col, Descriptions, Row, Space, Spin, Tag, Typography } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { lazy, Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { AddToProject } from '../components/AddToProject';
import { PageHead, SectionCard } from '../components/common';
import { ExportButtons, QcPanel, RelaxButton } from './BuilderPage';

const Viewer3D = lazy(() => import('../components/Viewer3D'));

export default function StructurePage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const q = useQuery({ queryKey: ['structure', id], queryFn: () => api.get(`/structures/${id}`) });
  if (q.isLoading) return <Spin style={{ margin: '20vh auto', display: 'block' }} />;
  if (q.error || !q.data) return <Alert type="error" message={(q.error as Error)?.message} />;
  const st: Json = q.data;
  const rx: Json = st.relax || {};
  const analyze = async () => {
    setBusy(true);
    try {
      await api.post(`/structures/${id}/analyze`);
      qc.invalidateQueries({ queryKey: ['structure', id] });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <PageHead
        title={st.name}
        sub={`${st.topology} · ${st.dimensionality}D · ${st.formula}`}
        extra={
          <Space>
            <AddToProject itemType="structure" itemId={st.id} size="middle" />
            <Button icon={<ReloadOutlined />} loading={busy} onClick={analyze}>
              {t('builder.pore')}
            </Button>
            <RelaxButton st={st} onSubmitted={() => nav('/jobs')} />
          </Space>
        }
      />
      <Row gutter={18}>
        <Col xs={24} xl={14}>
          <Suspense fallback={<Spin />}>
            <Viewer3D data={st.cif} format="cif" height={560} periodic />
          </Suspense>
          <div style={{ marginTop: 12 }}>
            <ExportButtons st={st} />
          </div>
        </Col>
        <Col xs={24} xl={10}>
          <SectionCard title={t('builder.qc')}>
            <QcPanel st={st} />
          </SectionCard>
          {st.parent_id ? (
            <SectionCard title={t('builder.relax')}>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label={t('builder.parent')}>
                  <Link to={`/structures/${st.parent_id}`}>#{st.parent_id}</Link>
                </Descriptions.Item>
                <Descriptions.Item label="engine">{rx.engine_name} ({rx.device})</Descriptions.Item>
                <Descriptions.Item label={t('builder.energy')}>{rx.energy_change_eV} (per molecule {rx.energy_per_molecule_eV})</Descriptions.Item>
                <Descriptions.Item label={t('builder.volume')}>{rx.volume_change_pct}%</Descriptions.Item>
                <Descriptions.Item label={t('builder.collapse')}>
                  <Tag color={rx.collapse_flag ? 'red' : 'green'}>{rx.collapse_flag ? t('common.yes') : t('common.no')}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="converged">
                  atoms {String(rx.converged_atoms)} · cell {String(rx.converged_cell)} · {rx.steps} steps · {rx.wall_time_s}s
                </Descriptions.Item>
              </Descriptions>
              <Button icon={<DownloadOutlined />} onClick={() => api.download(`/structures/${st.id}/trajectory`, {}, `relax_${st.id}.xyz`)}>
                {t('builder.trajectory')}
              </Button>
              <Typography.Paragraph className="muted" style={{ fontSize: 12, marginTop: 10 }}>
                {rx.license}
              </Typography.Paragraph>
            </SectionCard>
          ) : null}
          <SectionCard title={t('builder.info')}>
            <pre className="mono" style={{ fontSize: 11.5, whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify({ options: st.options, components: st.components, building: st.analysis?.build_info }, null, 2)}</pre>
          </SectionCard>
        </Col>
      </Row>
    </div>
  );
}
