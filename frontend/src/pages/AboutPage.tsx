import { Alert, Card, Col, Row, Table } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type Json } from '../api';
import { PageHead } from '../components/common';

export default function AboutPage() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ['datasources'], queryFn: () => api.get('/meta/data-sources') });
  const d: Json = q.data || { datasets: [], software: [] };
  return (
    <div>
      <PageHead title={t('about.title')} sub={t('about.sub')} />
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={t('about.disclaimerScore')} />
      <Alert type="warning" showIcon style={{ marginBottom: 18 }} message={t('about.disclaimerStructure')} />
      <Row gutter={18}>
        <Col xs={24} lg={12}>
          <Card title={<span className="display">{t('about.datasets')}</span>}>
            {(d.datasets as Json[]).map((x) => (
              <div key={x.key} style={{ marginBottom: 14 }}>
                <b>{x.name}</b> <span className="muted">{x.version}</span>
                <div>
                  <a href={x.url} target="_blank" rel="noreferrer">{x.url}</a> · {x.license}
                </div>
                <div className="muted" style={{ fontSize: 12.5 }}>{x.attribution}</div>
              </div>
            ))}
            <div className="muted" style={{ fontSize: 12.5 }}>
              RCSR — Reticular Chemistry Structure Resource (O'Keeffe, Peskov, Ramsden, Yaghi, Acc. Chem. Res. 2008, 41, 1782). Crystal structures are
              cited by CCDC deposition number; CSD-derived data are used under the operator's CSD licence.
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<span className="display">{t('about.software')}</span>}>
            <Table
              size="small"
              rowKey="name"
              pagination={false}
              dataSource={d.software}
              columns={[
                { title: 'Name', dataIndex: 'name', render: (n: string, r: Json) => <a href={r.url} target="_blank" rel="noreferrer">{n}</a> },
                { title: 'Licence', dataIndex: 'license' },
                { title: 'Citation', dataIndex: 'citation', render: (c: string) => <span className="muted" style={{ fontSize: 12 }}>{c}</span> },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
