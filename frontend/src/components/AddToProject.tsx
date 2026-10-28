import { Button, Dropdown, Modal, Select, Space, message } from 'antd';
import { FolderAddOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api';

export function AddToProject({ itemType, itemId, size = 'small' }: { itemType: string; itemId?: number | null; size?: 'small' | 'middle' }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api.get('/projects') });
  const [open, setOpen] = useState(false);
  const [pid, setPid] = useState<number | undefined>();
  if (!itemId) return null;
  const add = async (projectId: number) => {
    await api.post(`/projects/${projectId}/items`, { item_type: itemType, item_id: itemId });
    message.success(t('common.save'));
    qc.invalidateQueries({ queryKey: ['projects'] });
  };
  const list = (projects.data || []) as any[];
  return (
    <>
      <Dropdown
        menu={{
          items: [
            ...list.slice(0, 8).map((p) => ({ key: String(p.id), label: p.name, onClick: () => add(p.id) })),
            { type: 'divider' as const },
            { key: 'more', label: '…', onClick: () => setOpen(true) },
          ],
        }}
      >
        <Button size={size} icon={<FolderAddOutlined />}>
          {t('common.addToProject')}
        </Button>
      </Dropdown>
      <Modal open={open} onCancel={() => setOpen(false)} onOk={() => pid && add(pid).then(() => setOpen(false))} title={t('common.addToProject')}>
        <Space style={{ width: '100%' }}>
          <Select style={{ width: 360 }} value={pid} onChange={setPid} options={list.map((p) => ({ value: p.id, label: p.name }))} />
        </Space>
      </Modal>
    </>
  );
}
