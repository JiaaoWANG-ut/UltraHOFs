import { Alert, Button, Col, Descriptions, Row, Space, Spin, Tag } from 'antd';
import { ApartmentOutlined, ExperimentOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { AddToProject } from '../components/AddToProject';
import { BandTag, CopyText, MolSvg, PageHead, PrecedentPanel, ScoreBreakdown, SectionCard } from '../components/common';

export default function MoleculePage() {
  const { id } = useParams();
  const { t, i18n } = useTranslation();
  const zh = i18n.language === 'zh-CN';
  const nav = useNavigate();
  const q = useQuery({ queryKey: ['molecule', id], queryFn: () => api.get(`/molecules/${id}`) });
  if (q.isLoading) return <Spin style={{ margin: '20vh auto', display: 'block' }} />;
  if (q.error || !q.data) return <Alert type="error" message={(q.error as Error)?.message} />;
  const m: Json = q.data;
  const sd: Json = m.score_detail || {};
  return (
    <div>
      <PageHead
        title={m.name || m.formula}
        sub={`${m.origin}${m.is_experimental_tecton ? ' · experimental tecton' : ''}`}
        extra={
          <Space>
            <AddToProject itemType="molecule" itemId={m.id} size="middle" />
            <Button icon={<ExperimentOutlined />} onClick={() => nav(`/design/evaluate?smiles=${encodeURIComponent(m.smiles)}`)}>
              {t('common.evaluate')}
            </Button>
            <Button type="primary" icon={<ApartmentOutlined />} onClick={() => nav(`/builder?node=${encodeURIComponent(m.smiles)}`)}>
              {t('common.build')}
            </Button>
          </Space>
        }
      />
      <Row gutter={18}>
        <Col xs={24} lg={10}>
          <SectionCard title={m.formula}>
            <MolSvg svg={m.svg} />
            <CopyText text={m.smiles} />
            <Descriptions size="small" column={1} style={{ marginTop: 10 }}>
              <Descriptions.Item label="InChIKey">
                <span className="mono">{m.inchikey}</span>
              </Descriptions.Item>
              <Descriptions.Item label="MW">{m.mw}</Descriptions.Item>
              <Descriptions.Item label={t('design.synthons')}>
                {(m.synthons || []).map((s: Json) => (
                  <Tag key={s.type}>
                    {zh ? s.name_zh : s.name_en} ×{s.count}
                  </Tag>
                ))}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.score')}>
                <BandTag band={m.band} score={m.score} />
              </Descriptions.Item>
            </Descriptions>
          </SectionCard>
          {m.route ? (
            <SectionCard title={t('design.route')}>
              <ol style={{ paddingLeft: 18 }}>
                {(zh ? m.route.zh : m.route.en).map((s: string) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </SectionCard>
          ) : null}
        </Col>
        <Col xs={24} lg={14}>
          <SectionCard title={t('design.precedent')}>
            <PrecedentPanel precedent={m.precedent} />
          </SectionCard>
          {sd.components ? (
            <SectionCard title={t('design.breakdown')}>
              <ScoreBreakdown components={sd.components} />
            </SectionCard>
          ) : null}
        </Col>
      </Row>
    </div>
  );
}
