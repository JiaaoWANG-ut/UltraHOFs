import { Alert, Button, Card, Col, Form, Row, Select, Space, Table, Tag } from 'antd';
import { ApartmentOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type Json } from '../api';
import { MolSvg, PageHead, SectionCard } from '../components/common';
import { SmilesInput } from '../components/SmilesInput';

export default function PairsPage() {
  const { t, i18n } = useTranslation();
  const zh = i18n.language === 'zh-CN';
  const nav = useNavigate();
  const lib = useQuery({ queryKey: ['libraries'], queryFn: () => api.get('/libraries') });
  const [cation, setCation] = useState('NC(=[NH2+])c1ccc(C(c2ccc(C(N)=[NH2+])cc2)(c2ccc(C(N)=[NH2+])cc2)c2ccc(C(N)=[NH2+])cc2)cc1');
  const [anion, setAnion] = useState('[O-]C(=O)c1ccc(C([O-])=O)cc1');
  const evalPair = useMutation({ mutationFn: () => api.post('/pairs/evaluate', { cation, anion }) });
  const gen = useMutation({ mutationFn: (v: Json) => api.post('/pairs/generate', v) });
  const cores: Json[] = lib.data?.cores || [];
  const coreOpts = cores.map((c) => ({ value: c.key, label: `${zh ? c.name_zh : c.name_en} (${c.n_sites}-c)` }));
  const p: Json | undefined = evalPair.data;

  const buildLink = (cat: string, an: string, net?: string) => {
    const qs = new URLSearchParams({ node_a: cat, node_b: an });
    if (net) qs.set('net', net);
    nav(`/builder?${qs.toString()}`);
  };

  return (
    <div>
      <PageHead title={t('design.pairsTitle')} sub={t('design.pairsSub')} />
      <Row gutter={18}>
        <Col xs={24} lg={12}>
          <SectionCard title={t('design.evaluatePair')}>
            <div className="muted">{t('design.cation')}</div>
            <SmilesInput value={cation} onChange={setCation} />
            <div className="muted" style={{ marginTop: 12 }}>{t('design.anion')}</div>
            <SmilesInput value={anion} onChange={setAnion} />
            <Button type="primary" style={{ marginTop: 12 }} loading={evalPair.isPending} onClick={() => evalPair.mutate()}>
              {t('design.evaluatePair')}
            </Button>
            {evalPair.error ? <Alert type="error" showIcon style={{ marginTop: 10 }} message={(evalPair.error as Error).message} /> : null}
            {p ? (
              <Card size="small" style={{ marginTop: 14 }}>
                <Row gutter={10}>
                  <Col span={12}>
                    <MolSvg svg={p.cation.svg} />
                    <Tag>{p.cation.synthon}</Tag> <Tag>{p.cation.geometry}</Tag> <Tag>q = +{p.cation.charge}</Tag>
                  </Col>
                  <Col span={12}>
                    <MolSvg svg={p.anion.svg} />
                    <Tag>{p.anion.synthon}</Tag> <Tag>{p.anion.geometry}</Tag> <Tag>q = {p.anion.charge}</Tag>
                  </Col>
                </Row>
                <div style={{ marginTop: 10 }}>
                  <div>
                    {t('design.stoich')}: <b>{p.stoichiometry.cation} : {p.stoichiometry.anion}</b>
                  </div>
                  <div>
                    {t('design.complementarity')}: <b>{p.complementarity.score}</b> <span className="muted">{p.complementarity.motif}</span>
                  </div>
                  <div>
                    {t('design.netCompat')}: <b>{p.net_compatibility.score}</b> <span className="muted">{p.net_compatibility.note}</span>
                  </div>
                  <div className="score-big" style={{ fontSize: 40, marginTop: 8 }}>{p.score}</div>
                  {p.issues?.length ? <Alert type="warning" showIcon message={p.issues.join('; ')} /> : null}
                  <Alert type="info" showIcon style={{ marginTop: 8 }} message={zh ? p.disclaimer_zh : p.disclaimer_en} />
                  <Space style={{ marginTop: 10 }}>
                    {(p.net_compatibility.nets || []).map((n: string) => (
                      <Button key={n} icon={<ApartmentOutlined />} onClick={() => buildLink(p.cation.smiles, p.anion.smiles, n)}>
                        {n}
                      </Button>
                    ))}
                  </Space>
                </div>
              </Card>
            ) : null}
          </SectionCard>
        </Col>
        <Col xs={24} lg={12}>
          <SectionCard title={t('design.enumeratePairs')}>
            <Form
              layout="vertical"
              initialValues={{ cation_cores: ['tpm'], anion_cores: ['benzene_14', 'biphenyl_44'], cation_types: ['amidinium'], anion_types: ['carboxylate', 'sulfonate'], arms: ['none', 'phenylene'] }}
              onFinish={(v) => gen.mutate(v)}
            >
              <Form.Item name="cation_cores" label={`${t('design.cation')} · ${t('design.cores')}`}>
                <Select mode="multiple" options={coreOpts} />
              </Form.Item>
              <Form.Item name="cation_types" label={`${t('design.cation')} · ${t('design.synthons')}`}>
                <Select mode="multiple" options={(lib.data?.cation_fragments || []).map((x: string) => ({ value: x, label: x }))} />
              </Form.Item>
              <Form.Item name="anion_cores" label={`${t('design.anion')} · ${t('design.cores')}`}>
                <Select mode="multiple" options={coreOpts} />
              </Form.Item>
              <Form.Item name="anion_types" label={`${t('design.anion')} · ${t('design.synthons')}`}>
                <Select mode="multiple" options={(lib.data?.anion_fragments || []).map((x: string) => ({ value: x, label: x }))} />
              </Form.Item>
              <Form.Item name="arms" label={t('design.arms')}>
                <Select mode="multiple" options={(lib.data?.arms || []).map((a: Json) => ({ value: a.key, label: zh ? a.name_zh : a.name_en }))} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={gen.isPending}>
                {t('design.enumeratePairs')}
              </Button>
            </Form>
          </SectionCard>
        </Col>
      </Row>
      {gen.data ? (
        <SectionCard title={`${t('design.candidates')} (${gen.data.n})`}>
          <Table
            rowKey={(r: Json) => r.cation.smiles + r.anion.smiles}
            size="small"
            dataSource={gen.data.pairs}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: t('design.cation'), render: (_: unknown, r: Json) => <div style={{ width: 170 }}><MolSvg svg={r.cation.svg} /></div> },
              { title: t('design.anion'), render: (_: unknown, r: Json) => <div style={{ width: 170 }}><MolSvg svg={r.anion.svg} /></div> },
              { title: t('design.stoich'), render: (_: unknown, r: Json) => `${r.stoichiometry.cation}:${r.stoichiometry.anion}` },
              { title: t('design.complementarity'), render: (_: unknown, r: Json) => <span>{r.complementarity.score} <span className="muted" style={{ fontSize: 12 }}>{r.complementarity.motif}</span></span> },
              { title: t('design.netCompat'), render: (_: unknown, r: Json) => (r.net_compatibility.nets || []).map((n: string) => <Tag key={n}>{n}</Tag>) },
              { title: t('common.score'), dataIndex: 'score', sorter: (a: Json, b: Json) => a.score - b.score, defaultSortOrder: 'descend' as const },
              {
                title: '',
                render: (_: unknown, r: Json) => (
                  <Button size="small" icon={<ApartmentOutlined />} onClick={() => buildLink(r.cation.smiles, r.anion.smiles, r.net_compatibility.nets?.[0])}>
                    {t('common.build')}
                  </Button>
                ),
              },
            ]}
          />
        </SectionCard>
      ) : null}
    </div>
  );
}
