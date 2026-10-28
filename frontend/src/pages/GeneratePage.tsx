import { Alert, Button, Card, Checkbox, Col, Form, InputNumber, Popover, Row, Select, Space, Switch, Tag, Tooltip } from 'antd';
import { ApartmentOutlined, ExperimentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { api, type Json } from '../api';
import { AddToProject } from '../components/AddToProject';
import { BandTag, EmptyState, MolSvg, PageHead, SectionCard } from '../components/common';

export default function GeneratePage() {
  const { t, i18n } = useTranslation();
  const zh = i18n.language === 'zh-CN';
  const nav = useNavigate();
  const lib = useQuery({ queryKey: ['libraries'], queryFn: () => api.get('/libraries') });
  const [form] = Form.useForm();
  const [sortBy, setSortBy] = useState('score');
  const gen = useMutation({ mutationFn: (v: Json) => api.post('/molecules/generate', v) });
  const L: Json = lib.data || { cores: [], arms: [], synthons: [] };
  const res: Json | undefined = gen.data;
  const cands: Json[] = res?.candidates ? [...res.candidates] : [];
  if (sortBy === 'mw') cands.sort((a, b) => a.mw - b.mw);

  const coreGroups: Record<string, Json[]> = {};
  (L.cores as Json[]).forEach((c) => {
    const g = `${c.n_sites}-c · ${c.geometry}`;
    (coreGroups[g] ||= []).push(c);
  });

  return (
    <div>
      <PageHead title={t('design.generateTitle')} sub={t('design.generateSub')} />
      <Row gutter={18}>
        <Col xs={24} lg={8}>
          <SectionCard title={t('common.run')}>
            <Form
              form={form}
              layout="vertical"
              initialValues={{ cores: ['benzene_135', 'tpm', 'pyrene'], arms: ['none', 'phenylene'], synthons: ['carboxylic_acid', 'dat', 'pyridone'], min_sites: 3, max_heavy_atoms: 160, limit: 120, with_3d: true }}
              onFinish={(v) => gen.mutate(v)}
            >
              <Form.Item name="cores" label={t('design.cores')}>
                <Select
                  mode="multiple"
                  allowClear
                  options={Object.entries(coreGroups).map(([g, cs]) => ({ label: g, options: cs.map((c) => ({ value: c.key, label: zh ? c.name_zh : c.name_en })) }))}
                />
              </Form.Item>
              <Form.Item name="arms" label={t('design.arms')}>
                <Checkbox.Group options={(L.arms as Json[]).map((a) => ({ value: a.key, label: zh ? a.name_zh : a.name_en }))} />
              </Form.Item>
              <Form.Item name="synthons" label={t('design.synthons')}>
                <Select
                  mode="multiple"
                  allowClear
                  options={(L.synthons as Json[]).map((s) => ({
                    value: s.key,
                    label: (
                      <span>
                        {zh ? s.name_zh : s.name_en} <span className="muted">· {s.strength}</span>
                      </span>
                    ),
                  }))}
                />
              </Form.Item>
              <Row gutter={10}>
                <Col span={8}>
                  <Form.Item name="min_sites" label={t('design.minSites')}>
                    <InputNumber min={2} max={6} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="max_heavy_atoms" label={t('design.maxHeavy')}>
                    <InputNumber min={10} max={400} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="limit" label={t('design.limit')}>
                    <InputNumber min={1} max={5000} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="with_3d" label={t('design.with3d')} valuePropName="checked">
                <Switch />
              </Form.Item>
              <Button type="primary" htmlType="submit" icon={<ThunderboltOutlined />} loading={gen.isPending} block>
                {t('design.generate')}
              </Button>
            </Form>
            {gen.error ? <Alert type="error" showIcon style={{ marginTop: 12 }} message={(gen.error as Error).message} /> : null}
          </SectionCard>
        </Col>
        <Col xs={24} lg={16}>
          {res?.mode === 'job' ? (
            <Alert type="info" showIcon message={t('design.asJob')} description={<Link to="/jobs">{t('nav.jobs')} #{res.job.id}</Link>} />
          ) : null}
          {res?.mode === 'sync' ? (
            <>
              <Space style={{ marginBottom: 12, justifyContent: 'space-between', width: '100%' }}>
                <span className="muted">
                  {t('design.candidates')}: <b>{res.n}</b> / {res.n_combinations} {t('design.combos')}
                </span>
                <Select size="small" value={sortBy} onChange={setSortBy} options={[{ value: 'score', label: t('common.score') }, { value: 'mw', label: 'MW' }]} />
              </Space>
              <Row gutter={[14, 14]}>
                {cands.map((c) => (
                  <Col xs={24} md={12} xl={8} key={c.molecule_id}>
                    <Card size="small" className="mol-card">
                      <MolSvg svg={c.svg} height={170} />
                      <Space size={4} wrap>
                        <BandTag band={c.band} score={c.score} />
                        {c.precedent === 'exact' ? <Tag color="green">{t('design.reported')}</Tag> : null}
                        <Tag>{c.n_connect}-c</Tag>
                        {c.geometry ? <Tag>{c.geometry}</Tag> : null}
                      </Space>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                        {c.core} · {c.arm} · {c.synthon} · {c.formula}
                      </div>
                      <Space style={{ marginTop: 8 }} wrap>
                        <Tooltip title={t('design.evaluate')}>
                          <Button size="small" icon={<ExperimentOutlined />} onClick={() => nav(`/design/evaluate?smiles=${encodeURIComponent(c.smiles)}`)} />
                        </Tooltip>
                        <Tooltip title={t('common.build')}>
                          <Button size="small" icon={<ApartmentOutlined />} onClick={() => nav(`/builder?node=${encodeURIComponent(c.smiles)}`)} />
                        </Tooltip>
                        <Popover
                          title={t('design.route')}
                          content={
                            <ol style={{ paddingLeft: 18, margin: 0, maxWidth: 420 }}>
                              {(zh ? c.route.zh : c.route.en).map((s: string) => (
                                <li key={s}>{s}</li>
                              ))}
                            </ol>
                          }
                        >
                          <Button size="small">{t('design.route')}</Button>
                        </Popover>
                        <AddToProject itemType="molecule" itemId={c.molecule_id} />
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            </>
          ) : null}
          {!res ? <EmptyState text={t('design.generateSub')} /> : null}
        </Col>
      </Row>
    </div>
  );
}
