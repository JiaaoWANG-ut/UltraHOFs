import { Button, Card, Empty, Popover, Space, Tag, Tooltip, Typography, message } from 'antd';
import { CopyOutlined, DownloadOutlined, LinkOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api, type Json } from '../api';
import { brand } from '../theme';

export function MolSvg({ svg, height }: { svg?: string; height?: number }) {
  if (!svg) return <div style={{ height: height || 160 }} />;
  return <div className="mol-svg" style={height ? { height, display: 'flex', alignItems: 'center' } : undefined} dangerouslySetInnerHTML={{ __html: svg }} />;
}

export function CopyText({ text, mono = true }: { text: string; mono?: boolean }) {
  const { t } = useTranslation();
  return (
    <Space size={4} align="start">
      <span className={mono ? 'mono' : undefined}>{text}</span>
      <Tooltip title={t('common.copy')}>
        <Button
          size="small"
          type="text"
          icon={<CopyOutlined />}
          onClick={() => navigator.clipboard.writeText(text).then(() => message.success(t('common.copied')))}
        />
      </Tooltip>
    </Space>
  );
}

const EV_KEYS = ['crystal_structure_reported', 'extended_hbond_network', 'geometric_porosity', 'activation_retained', 'measured_porosity'];

export function EvidenceDots({ evidence }: { evidence: Json }) {
  const { t } = useTranslation();
  const color = (v: string) => (v === 'yes' ? '#3F6B4F' : v === 'no' ? '#9B3B32' : '#C9C3B6');
  return (
    <Space size={3}>
      {EV_KEYS.map((k) => {
        const v = typeof evidence?.[k] === 'string' ? evidence[k] : evidence?.[k]?.value || 'unknown';
        return (
          <Tooltip key={k} title={`${t(`evidence.${k}`)}: ${t(`evidence.${v}`)}`}>
            <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 9, background: color(v) }} />
          </Tooltip>
        );
      })}
    </Space>
  );
}

export function EvidenceTable({ evidence }: { evidence: Json }) {
  const { t } = useTranslation();
  return (
    <div>
      {EV_KEYS.map((k) => {
        const e = evidence?.[k] || { value: 'unknown' };
        return (
          <div key={k} style={{ display: 'flex', gap: 12, padding: '7px 0', borderBottom: '1px dashed var(--line)' }}>
            <div style={{ width: 210 }}>{t(`evidence.${k}`)}</div>
            <div style={{ width: 70 }} className={`evidence-${e.value}`}>
              <b>{t(`evidence.${e.value}`)}</b>
            </div>
            <div style={{ width: 80 }}>{e.source ? <Tag>{String(t(`evidence.${e.source}`, { defaultValue: e.source }))}</Tag> : null}</div>
            <div className="muted" style={{ flex: 1, fontSize: 12.5 }}>{e.note}</div>
          </div>
        );
      })}
    </div>
  );
}

export function StatusTag({ status }: { status: string }) {
  const { t } = useTranslation();
  const color = ({ verified: 'green', auto: 'blue', needs_review: 'gold', candidate: 'purple', rejected: 'red' } as Record<string, string>)[status] || 'default';
  return <Tag color={color}>{t(`status.${status}`, status)}</Tag>;
}

export function BandTag({ band, score }: { band?: string; score?: number | null }) {
  const { t } = useTranslation();
  if (score === undefined || score === null) return null;
  const color = band === 'high' ? '#3F6B4F' : band === 'medium' ? '#A8742A' : '#9B3B32';
  return (
    <Tag color={color} style={{ fontWeight: 600 }}>
      {score.toFixed(0)} · {t(`design.band.${band}`)}
    </Tag>
  );
}

export function Citation({ refd, compact = false }: { refd: Json; compact?: boolean }) {
  const { t } = useTranslation();
  const authors = (refd.authors || []) as Json[];
  const max = compact ? 3 : 12;
  const names = authors
    .slice(0, max)
    .map((a) => `${a.family}${a.given ? ', ' + String(a.given).split(/[\s-]+/).filter(Boolean).map((x: string) => x[0] + '.').join(' ') : ''}`);
  if (authors.length > max) names.push('et al.');
  const journal = refd.journal_abbrev || refd.journal;
  return (
    <div className="citation">
      {names.join('; ')}
      {names.length ? ' ' : ''}
      <span style={{ fontWeight: 600 }}>{refd.title || refd.raw_citation}</span>. <em>{journal}</em> <b>{refd.year}</b>
      {refd.volume ? <>, <em>{refd.volume}</em></> : null}
      {refd.pages ? `, ${refd.pages}` : ''}.
      {refd.doi ? (
        <>
          {' '}
          <a href={`https://doi.org/${refd.doi}`} target="_blank" rel="noreferrer">
            <LinkOutlined /> {refd.doi}
          </a>
        </>
      ) : null}
      {!compact && refd.id ? (
        <Space style={{ marginLeft: 10 }} size={4}>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => api.download(`/references/${refd.id}/export`, { format: 'bibtex' }, `ref_${refd.id}.bib`)}>
            {t('entry.bibtex')}
          </Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => api.download(`/references/${refd.id}/export`, { format: 'ris' }, `ref_${refd.id}.ris`)}>
            {t('entry.ris')}
          </Button>
        </Space>
      ) : null}
    </div>
  );
}

export function ScoreRadar({ components, height = 300 }: { components: Json[]; height?: number }) {
  const { i18n } = useTranslation();
  const zh = i18n.language === 'zh-CN';
  const option = {
    radar: {
      indicator: components.map((c) => ({ name: zh ? c.label_zh : c.label_en, max: 1 })),
      radius: '62%',
      axisName: { color: '#5B6067', fontSize: 11, fontFamily: zh ? 'Zhuque Fangsong' : 'Inter' },
      splitLine: { lineStyle: { color: '#E4DED2' } },
      splitArea: { areaStyle: { color: ['#FBFAF7', '#F6F4EF'] } },
      axisLine: { lineStyle: { color: '#E4DED2' } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: components.map((c) => c.score), name: 'score' }],
        lineStyle: { color: brand.gold, width: 2 },
        areaStyle: { color: 'rgba(176,141,87,0.22)' },
        itemStyle: { color: brand.indigo },
        symbolSize: 4,
      },
    ],
  };
  return <ReactECharts option={option} style={{ height }} />;
}

export function ScoreBreakdown({ components }: { components: Json[] }) {
  const { i18n } = useTranslation();
  const zh = i18n.language === 'zh-CN';
  return (
    <div>
      {components.map((c) => (
        <div key={c.key} style={{ display: 'grid', gridTemplateColumns: '150px 60px 1fr', gap: 10, padding: '7px 0', borderBottom: '1px dashed var(--line)' }}>
          <div className={zh ? 'zh' : undefined}>{zh ? c.label_zh : c.label_en}</div>
          <div>
            <b>{(c.score * 100).toFixed(0)}</b>
            <span className="muted" style={{ fontSize: 11 }}> ×{c.weight}</span>
          </div>
          <div className="muted" style={{ fontSize: 12.5 }}>{zh ? c.explain_zh : c.explain_en}</div>
        </div>
      ))}
    </div>
  );
}

export function PrecedentPanel({ precedent }: { precedent: Json }) {
  const { t } = useTranslation();
  if (!precedent) return null;
  const statusColor = ({ exact: 'green', same_parent: 'cyan', same_skeleton: 'blue', analogues: 'gold', none: 'default' } as Record<string, string>)[precedent.status as string];
  const entryLine = (e: Json) => (
    <div key={`${e._k}-${e.id}`} style={{ padding: '6px 0', borderBottom: '1px dashed var(--line)' }}>
      <Link to={`/database/${e.id}`}>
        <b>{e.name || `#${e.id}`}</b>
      </Link>{' '}
      {e.ccdc_numbers?.length ? <Tag>CCDC {e.ccdc_numbers[0]}</Tag> : null}
      {e.reference ? (
        <span className="muted" style={{ fontSize: 12.5 }}>
          {' '}
          {e.reference.authors?.[0]} et al., <em>{e.reference.journal}</em> {e.reference.year}
          {e.reference.doi ? (
            <>
              {' '}
              · <a href={`https://doi.org/${e.reference.doi}`} target="_blank" rel="noreferrer">{e.reference.doi}</a>
            </>
          ) : null}
        </span>
      ) : null}
    </div>
  );
  const lists = ['exact', 'same_parent', 'same_skeleton'].flatMap((k) => (precedent[k] || []).map((e: Json) => ({ ...e, _k: k })));
  return (
    <div>
      <Tag color={statusColor} style={{ fontSize: 13, padding: '3px 10px', marginBottom: 10 }}>
        {t(`design.${precedent.status === 'none' ? 'noneFound' : precedent.status}`)}
      </Tag>
      {lists.map(entryLine)}
      {precedent.similar?.length ? (
        <div style={{ marginTop: 10 }}>
          <Typography.Text type="secondary">{t('design.similarity')}</Typography.Text>
          {precedent.similar.map((s: Json) => (
            <div key={s.molecule_id} style={{ padding: '4px 0' }}>
              <Tag>{(s.similarity * 100).toFixed(0)}%</Tag>
              <Popover content={<span className="mono">{s.smiles}</span>}>
                <span className="mono" style={{ fontSize: 11.5 }}>
                  {s.smiles.slice(0, 48)}
                  {s.smiles.length > 48 ? '…' : ''}
                </span>
              </Popover>
              {(s.entries || []).slice(0, 2).map((e: Json) => (
                <Link key={e.id} to={`/database/${e.id}`} style={{ marginLeft: 8 }}>
                  {e.name || `#${e.id}`}
                </Link>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({ text }: { text?: string }) {
  return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={text} />;
}

export function SectionCard({ title, extra, children }: { title: ReactNode; extra?: ReactNode; children: ReactNode }) {
  return (
    <Card title={<span className="display" style={{ fontSize: 18 }}>{title}</span>} extra={extra} variant="outlined" style={{ marginBottom: 18 }}>
      {children}
    </Card>
  );
}

export function PageHead({ title, sub, extra }: { title: ReactNode; sub?: ReactNode; extra?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub ? <div className="sub">{sub}</div> : null}
      </div>
      {extra}
    </div>
  );
}

/** Columns shared by the net-recommendation tables (Evaluate + Builder). */
export function useNetColumns() {
  const { t } = useTranslation();
  const warn = (bad: boolean, text: ReactNode) => <span style={bad ? { color: '#B4691F', fontWeight: 600 } : undefined}>{text}</span>;
  return [
    {
      title: t('builder.net'),
      dataIndex: 'net',
      render: (n: string, x: Json) => (
        <b>
          {n}
          {x.precedent ? <Tag color="gold" style={{ marginLeft: 6 }}>HOF</Tag> : null}
          {x.fit_ok === false ? <Tag color="orange" style={{ marginLeft: 4 }}>{t('builder.poorFit')}</Tag> : null}
        </b>
      ),
    },
    { title: 'dim', dataIndex: 'dim', render: (d: number) => `${d}D` },
    {
      title: <Tooltip title={t('builder.fitHelp')}>RMSD</Tooltip>,
      key: 'fit',
      render: (_: unknown, x: Json) => (x.node_fit ?? x.rmsd),
    },
    {
      title: <Tooltip title={t('builder.fitHelp')}>∠</Tooltip>,
      dataIndex: 'synthon_angle',
      render: (a: number | null | undefined) => (a === null || a === undefined ? '—' : warn(a > 15, `${a}°`)),
    },
    {
      title: <Tooltip title={t('builder.fitHelp')}>ΔX</Tooltip>,
      dataIndex: 'x_mismatch',
      render: (d: number | undefined) => (d === undefined ? '—' : warn(d > 0.3, `${d} Å`)),
    },
  ];
}
