import { Button, Card, Col, Form, Input, List, Modal, Popconfirm, Row, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { EmptyState, PageHead } from '../components/common';

const LINK: Record<string, (id: number) => string> = {
  molecule: (id) => `/molecules/${id}`,
  structure: (id) => `/structures/${id}`,
  hof_entry: (id) => `/database/${id}`,
  job: () => `/jobs`,
};

export default function ProjectsPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const list = useQuery({ queryKey: ['projects'], queryFn: () => api.get('/projects') });
  const detail = useQuery({ queryKey: ['project', id], queryFn: () => api.get(`/projects/${id}`), enabled: !!id });

  const create = async (v: Json) => {
    const p = await api.post('/projects', v);
    setOpen(false);
    qc.invalidateQueries({ queryKey: ['projects'] });
    nav(`/projects/${p.id}`);
  };
  const removeItem = async (itemId: number) => {
    await api.del(`/projects/${id}/items/${itemId}`);
    qc.invalidateQueries({ queryKey: ['project', id] });
  };
  const removeProject = async () => {
    await api.del(`/projects/${id}`);
    qc.invalidateQueries({ queryKey: ['projects'] });
    nav('/projects');
  };

  return (
    <div>
      <PageHead title={t('projects.title')} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t('projects.new')}</Button>} />
      <Row gutter={18}>
        <Col xs={24} md={8}>
          <Card size="small">
            {(list.data || []).length ? (
              <List
                dataSource={list.data || []}
                renderItem={(p: Json) => (
                  <List.Item style={{ cursor: 'pointer', background: String(p.id) === id ? '#F3EBDD' : undefined, padding: '10px 12px' }} onClick={() => nav(`/projects/${p.id}`)}>
                    <List.Item.Meta title={<span className="display" style={{ fontSize: 17 }}>{p.name}</span>} description={p.description} />
                    <Tag>{p.n_items}</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <EmptyState text={t('projects.empty')} />
            )}
          </Card>
        </Col>
        <Col xs={24} md={16}>
          {detail.data ? (
            <Card
              title={<span className="display" style={{ fontSize: 20 }}>{detail.data.name}</span>}
              extra={
                <Popconfirm title={t('common.delete') + '?'} onConfirm={removeProject}>
                  <Button danger size="small">{t('common.delete')}</Button>
                </Popconfirm>
              }
            >
              <p className="muted">{detail.data.description}</p>
              <List
                dataSource={detail.data.items || []}
                renderItem={(it: Json) => (
                  <List.Item
                    actions={[
                      <Link key="o" to={LINK[it.item_type](it.item_id)}>{t('common.open')}</Link>,
                      <Button key="d" type="text" danger size="small" onClick={() => removeItem(it.id)}>
                        {t('common.delete')}
                      </Button>,
                    ]}
                  >
                    <Space>
                      <Tag>{it.item_type}</Tag>
                      <span>{it.label}</span>
                      {it.smiles ? <span className="mono muted" style={{ fontSize: 11 }}>{String(it.smiles).slice(0, 60)}</span> : null}
                    </Space>
                  </List.Item>
                )}
              />
            </Card>
          ) : (
            <EmptyState />
          )}
        </Col>
      </Row>
      <Modal open={open} onCancel={() => setOpen(false)} footer={null} title={t('projects.new')} destroyOnHidden>
        <Form layout="vertical" onFinish={create}>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t('projects.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            {t('common.save')}
          </Button>
        </Form>
      </Modal>
    </div>
  );
}
