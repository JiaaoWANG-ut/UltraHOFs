import { Alert, Button, Input, Modal, Space, Spin } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';
import { MolSvg } from './common';

const KetcherEditor = lazy(() => import('./KetcherEditor'));

interface Props {
  value?: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  preview?: boolean;
  rows?: number;
}

export function SmilesInput({ value = '', onChange, placeholder, preview = true, rows = 2 }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [svg, setSvg] = useState<string>('');
  const [err, setErr] = useState<string>('');
  const ketcherRef = useRef<any>(null);

  useEffect(() => {
    if (!preview || !value.trim()) {
      setSvg('');
      setErr('');
      return;
    }
    const h = setTimeout(() => {
      api
        .post('/molecules/depict', { input: value, width: 300, height: 200 })
        .then((d) => {
          setSvg(d.svg);
          setErr('');
        })
        .catch((e) => {
          setSvg('');
          setErr(e.message);
        });
    }, 450);
    return () => clearTimeout(h);
  }, [value, preview]);

  const apply = async () => {
    if (ketcherRef.current) {
      const smi = await ketcherRef.current.getSmiles();
      onChange?.(smi);
    }
    setOpen(false);
  };

  return (
    <div>
      <Space.Compact style={{ width: '100%' }}>
        <Input.TextArea className="mono" rows={rows} value={value} placeholder={placeholder || 'SMILES'} onChange={(e) => onChange?.(e.target.value.trim())} />
        <Button icon={<EditOutlined />} style={{ height: 'auto' }} onClick={() => setOpen(true)}>
          {t('common.draw')}
        </Button>
      </Space.Compact>
      {preview && (svg || err) ? (
        <div style={{ marginTop: 8, maxWidth: 300 }}>{err ? <Alert type="warning" showIcon message={err} /> : <MolSvg svg={svg} />}</div>
      ) : null}
      <Modal open={open} onCancel={() => setOpen(false)} onOk={apply} width={1100} title={t('common.draw')} destroyOnHidden okText={t('common.confirm')} cancelText={t('common.cancel')}>
        <div style={{ height: 600, position: 'relative' }}>
          <Suspense fallback={<Spin style={{ marginTop: 200, marginLeft: '48%' }} />}>
            <KetcherEditor initial={value} onReady={(k) => (ketcherRef.current = k)} />
          </Suspense>
        </div>
      </Modal>
    </div>
  );
}
