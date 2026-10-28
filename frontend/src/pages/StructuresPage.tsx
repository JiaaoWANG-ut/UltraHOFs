import { Button, Popconfirm, Space, Table, Tag } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, type Json } from '../api';
import { PageHead } from '../components/common';

export default function StructuresPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['structures'], queryFn: () => api.get('/structures', { size: 200 }) });
  const del = async (id: number) => {
    await api.del(`/structures/${id}`);
    qc.invalidateQueries({ queryKey: ['structures'] });
  };
  return (
    <div>
      <PageHead title={t('builder.myStructures')} sub={t('builder.sub')} extra={<Link to="/builder"><Button type="primary">{t('builder.build')}</Button></Link>} />
      <Table
        rowKey="id"
        loading={q.isLoading}
        dataSource={q.data?.items || []}
        columns={[
          { title: '#', dataIndex: 'id', width: 70 },
          { title: t('common.name'), dataIndex: 'name', render: (n: string, r: Json) => <Link to={`/structures/${r.id}`}>{n}</Link> },
          { title: t('builder.net'), dataIndex: 'topology', render: (n: string, r: Json) => <Tag>{n} · {r.dimensionality}D</Tag> },
          { title: 'formula', dataIndex: 'formula', render: (f: string) => <span className="mono">{f}</span> },
          { title: 'atoms', dataIndex: 'n_atoms' },
          { title: t('entry.density'), dataIndex: 'density' },
          { title: 'QC', dataIndex: 'qc', render: (qc: Json) => <Tag color={qc?.status === 'ok' ? 'green' : qc?.status === 'warning' ? 'gold' : 'red'}>{qc?.status}</Tag> },
          { title: t('common.status'), dataIndex: 'status', render: (s: string) => <Tag color={s === 'relaxed' ? 'blue' : undefined}>{s}</Tag> },
          { title: t('common.created'), dataIndex: 'created_at', render: (d: string) => d?.slice(0, 16).replace('T', ' ') },
          {
            title: t('common.actions'),
            render: (_: unknown, r: Json) => (
              <Space>
                <Link to={`/structures/${r.id}`}>{t('common.open')}</Link>
                <Popconfirm title={t('common.delete') + '?'} onConfirm={() => del(r.id)}>
                  <Button size="small" danger type="text">
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
