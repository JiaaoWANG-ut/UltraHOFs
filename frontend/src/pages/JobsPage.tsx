import { Button, Drawer, Progress, Space, Table, Tag, Typography } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, type Json } from '../api';
import { PageHead } from '../components/common';

const COLORS: Record<string, string> = { queued: 'default', running: 'processing', succeeded: 'success', failed: 'error', cancelled: 'warning', queued_slurm: 'purple' };

export default function JobsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [sel, setSel] = useState<Json | null>(null);
  const q = useQuery({
    queryKey: ['jobs'],
    queryFn: () => api.get('/jobs', { size: 200 }),
    refetchInterval: (query) => ((query.state.data as Json)?.items?.some((j: Json) => ['queued', 'running'].includes(j.status)) ? 3000 : false),
  });
  const detail = useQuery({ queryKey: ['job', sel?.id], queryFn: () => api.get(`/jobs/${sel!.id}`), enabled: !!sel, refetchInterval: 4000 });
  const log = useQuery({ queryKey: ['joblog', sel?.id], queryFn: () => api.text(`/jobs/${sel!.id}/log`), enabled: !!sel, refetchInterval: 4000 });
  const cancel = async (id: number) => {
    await api.post(`/jobs/${id}/cancel`);
    qc.invalidateQueries({ queryKey: ['jobs'] });
  };
  const d: Json = detail.data || sel || {};
  return (
    <div>
      <PageHead title={t('jobs.title')} sub="relax · generate_batch · analyze" />
      <Table
        rowKey="id"
        loading={q.isLoading}
        dataSource={q.data?.items || []}
        onRow={(r: Json) => ({ onClick: () => setSel(r), style: { cursor: 'pointer' } })}
        columns={[
          { title: '#', dataIndex: 'id', width: 70 },
          { title: t('jobs.type'), dataIndex: 'type' },
          { title: t('common.status'), dataIndex: 'status', render: (s: string) => <Tag color={COLORS[s]}>{s}</Tag> },
          { title: t('jobs.progress'), dataIndex: 'progress', width: 180, render: (p: number, r: Json) => <Progress percent={Math.round((p || 0) * 100)} size="small" status={r.status === 'failed' ? 'exception' : r.status === 'succeeded' ? 'success' : 'active'} /> },
          { title: t('jobs.message'), dataIndex: 'message', ellipsis: true },
          { title: t('common.created'), dataIndex: 'created_at', render: (d: string) => d?.slice(0, 16).replace('T', ' ') },
          {
            title: t('common.actions'),
            render: (_: unknown, r: Json) => (
              <Space onClick={(e) => e.stopPropagation()}>
                {r.result?.structure_id ? <Link to={`/structures/${r.result.structure_id}`}>{t('jobs.result')}</Link> : null}
                {['queued', 'running'].includes(r.status) ? (
                  <Button size="small" danger onClick={() => cancel(r.id)}>
                    {t('jobs.cancel')}
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      <Drawer open={!!sel} onClose={() => setSel(null)} width={720} title={`${t('nav.jobs')} #${d.id} · ${d.type}`}>
        <Space style={{ marginBottom: 12 }}>
          <Tag color={COLORS[d.status]}>{d.status}</Tag>
          <span className="muted">{d.message}</span>
        </Space>
        {d.error ? <pre className="mono" style={{ whiteSpace: 'pre-wrap', color: '#9B3B32', fontSize: 11.5 }}>{d.error}</pre> : null}
        {d.result?.structure_id ? (
          <div style={{ marginBottom: 12 }}>
            <Link to={`/structures/${d.result.structure_id}`}>→ {t('jobs.result')} #{d.result.structure_id}</Link>
          </div>
        ) : null}
        {d.type === 'generate_batch' && d.result?.candidates ? (
          <Table
            size="small"
            rowKey="molecule_id"
            dataSource={d.result.candidates}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: 'score', dataIndex: 'score' },
              { title: 'SMILES', dataIndex: 'smiles', render: (s: string, r: Json) => <Link to={`/molecules/${r.molecule_id}`} className="mono">{s.slice(0, 60)}</Link> },
              { title: 'core', dataIndex: 'core' },
              { title: 'synthon', dataIndex: 'synthon' },
            ]}
          />
        ) : null}
        <Typography.Title level={5}>{t('jobs.log')}</Typography.Title>
        <pre className="mono" style={{ background: '#FBFAF7', border: '1px solid var(--line)', padding: 10, maxHeight: 360, overflow: 'auto', fontSize: 11.5 }}>{log.data || '—'}</pre>
        <Typography.Title level={5}>params</Typography.Title>
        <pre className="mono" style={{ fontSize: 11.5 }}>{JSON.stringify(d.params, null, 2)}</pre>
      </Drawer>
    </div>
  );
}
