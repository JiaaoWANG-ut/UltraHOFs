import { Alert, Button, Col, InputNumber, Row, Space, Table, Tag, Typography } from 'antd';
import { ApartmentOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { AddToProject } from '../components/AddToProject';
import { BandTag, CopyText, MolSvg, PageHead, PrecedentPanel, ScoreBreakdown, ScoreRadar, SectionCard, useNetColumns } from '../components/common';
import { SmilesInput } from '../components/SmilesInput';

const Viewer3D = lazy(() => import('../components/Viewer3D'));

const EXAMPLES = [
  ['TMA', 'OC(=O)c1cc(C(O)=O)cc(C(O)=O)c1'],
  ['MTB', 'OC(=O)c1ccc(C(c2ccc(C(O)=O)cc2)(c2ccc(C(O)=O)cc2)c2ccc(C(O)=O)cc2)cc1'],
  ['TTBI', 'O=c1[nH]c2cc3c(cc2[nH]1)C1c2cc4[nH]c(=O)[nH]c4cc2C3c2cc3[nH]c(=O)[nH]c3cc21'],
  ['H4TBAPy', 'OC(=O)c1ccc(-c2cc(-c3ccc(C(O)=O)cc3)c3ccc4c(-c5ccc(C(O)=O)cc5)cc(-c5ccc(C(O)=O)cc5)c5ccc2c3c45)cc1'],
];

export default function EvaluatePage() {
  const { t, i18n } = useTranslation();
  const netColumns = useNetColumns();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [smiles, setSmiles] = useState(params.get('smiles') || '');
  const [nConfs, setNConfs] = useState(8);
  const [molblock, setMolblock] = useState<string>('');
  const ev = useMutation({ mutationFn: (s: string) => api.post('/molecules/evaluate', { input: s, n_confs: nConfs }) });
  const r: Json | undefined = ev.data;

  useEffect(() => {
    if (params.get('smiles')) ev.mutate(params.get('smiles')!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!r?.smiles) return;
    setMolblock('');
    api.post('/molecules/molblock', { input: r.smiles }).then((d) => setMolblock(d.molblock)).catch(() => setMolblock(''));
  }, [r?.smiles]);

  const sc: Json | undefined = r?.score;
  return (
    <div>
      <PageHead title={t('design.evaluateTitle')} sub={t('design.evaluateSub')} />
      <Row gutter={18}>
        <Col xs={24} lg={8}>
          <SectionCard title={t('design.input')}>
            <SmilesInput value={smiles} onChange={setSmiles} rows={3} />
            <Space wrap style={{ marginTop: 10 }}>
              {EXAMPLES.map(([n, s]) => (
                <Tag key={n} style={{ cursor: 'pointer' }} onClick={() => setSmiles(s)}>
                  {n}
                </Tag>
              ))}
            </Space>
            <Space style={{ marginTop: 14 }}>
              <span className="muted">conformers</span>
              <InputNumber min={1} max={30} value={nConfs} onChange={(v) => setNConfs(v || 8)} />
              <Button type="primary" icon={<ExperimentOutlined />} loading={ev.isPending} disabled={!smiles} onClick={() => ev.mutate(smiles)}>
                {t('design.evaluate')}
              </Button>
            </Space>
            {ev.error ? <Alert style={{ marginTop: 12 }} type="error" showIcon message={(ev.error as Error).message} /> : null}
          </SectionCard>
          {r ? (
            <SectionCard title="3D">
              <Suspense fallback={null}>{molblock ? <Viewer3D data={molblock} format="mol" height={300} controls={false} /> : null}</Suspense>
            </SectionCard>
          ) : null}
        </Col>
        <Col xs={24} lg={16}>
          {r && sc ? (
            <>
              <SectionCard
                title={t('common.score')}
                extra={
                  <Space>
                    <AddToProject itemType="molecule" itemId={r.molecule_id} />
                    <Button icon={<ApartmentOutlined />} onClick={() => nav(`/builder?node=${encodeURIComponent(r.smiles)}`)}>
                      {t('common.build')}
                    </Button>
                  </Space>
                }
              >
                <Row gutter={16} align="middle">
                  <Col xs={24} md={9}>
                    <MolSvg svg={r.svg} />
                    <CopyText text={r.smiles} />
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{r.keys?.formula} · MW {r.keys?.mw}</div>
                  </Col>
                  <Col xs={24} md={6} style={{ textAlign: 'center' }}>
                    <div className="score-big">{sc.score.toFixed(0)}</div>
                    <BandTag band={sc.band} score={sc.score} />
                    {r.percentile !== null && r.percentile !== undefined ? (
                      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                        {t('design.percentile')}: <b>{r.percentile}%</b>
                      </div>
                    ) : null}
                    <div className="muted" style={{ marginTop: 6, fontSize: 11.5 }}>Σw·s {sc.weighted_sum} × gate {sc.gate}</div>
                  </Col>
                  <Col xs={24} md={9}>
                    <ScoreRadar components={sc.components} height={260} />
                  </Col>
                </Row>
                <Alert type="info" showIcon style={{ marginTop: 6 }} message={t('design.disclaimer')} />
                {sc.flags?.length ? (
                  <div style={{ marginTop: 12 }}>
                    {sc.flags.map((f: Json, i: number) => (
                      <Alert key={i} style={{ marginTop: 6 }} type={f.level === 'bad' ? 'error' : f.level === 'warn' ? 'warning' : 'info'} message={i18n.language === 'zh-CN' ? f.zh : f.en} showIcon />
                    ))}
                  </div>
                ) : null}
              </SectionCard>
              <Row gutter={18}>
                <Col xs={24} xl={13}>
                  <SectionCard title={t('design.breakdown')}>
                    <ScoreBreakdown components={sc.components} />
                    {sc.geometry ? (
                      <div className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
                        {t('design.geometry')}: <b>{sc.geometry.geometry}</b> · {sc.geometry.n_confs} conformers ({sc.geometry.forcefield})
                      </div>
                    ) : null}
                  </SectionCard>
                </Col>
                <Col xs={24} xl={11}>
                  <SectionCard title={t('design.precedent')}>
                    <PrecedentPanel precedent={r.precedent} />
                  </SectionCard>
                  <SectionCard title={t('design.nets')}>
                    {r.nets?.available ? (
                      <Table
                        size="small"
                        rowKey="net"
                        pagination={false}
                        dataSource={r.nets.nets}
                        columns={[
                          ...netColumns,
                          {
                            title: '',
                            render: (_: unknown, x: Json) => (
                              <Button size="small" onClick={() => nav(`/builder?node=${encodeURIComponent(r.smiles)}&net=${x.net}`)}>
                                {t('common.build')}
                              </Button>
                            ),
                          },
                        ]}
                      />
                    ) : (
                      <Typography.Text type="secondary">{r.nets?.reason}</Typography.Text>
                    )}
                  </SectionCard>
                </Col>
              </Row>
            </>
          ) : (
            <div className="panel" style={{ minHeight: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span className="muted zh" style={{ fontSize: 16, letterSpacing: '0.1em' }}>{t('design.evaluateSub')}</span>
            </div>
          )}
        </Col>
      </Row>
    </div>
  );
}
