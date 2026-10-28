import { Alert, Button, Card, Col, Form, Input, InputNumber, Modal, Row, Select, Space, Switch, Table, Tabs, Tag, Upload, message } from 'antd';
import { MinusCircleOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';
import { api, type Json } from '../api';
import { useAuth } from '../auth';
import { Citation, MolSvg, PageHead, StatusTag } from '../components/common';
import { SmilesInput } from '../components/SmilesInput';

function Queue() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [status, setStatus] = useState('needs_review');
  const q = useQuery({ queryKey: ['queue', status], queryFn: () => api.get('/curation/queue', { status, size: 200 }) });
  const setEntryStatus = async (id: number, s: string) => {
    await api.patch(`/hofs/${id}`, { curation_status: s });
    qc.invalidateQueries({ queryKey: ['queue'] });
  };
  return (
    <div>
      <Select value={status} onChange={setStatus} style={{ width: 220, marginBottom: 12 }} options={['needs_review', 'candidate', 'rejected', 'auto', 'verified'].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      <Table
        rowKey="id"
        size="small"
        loading={q.isLoading}
        dataSource={q.data?.items || []}
        columns={[
          { title: '', dataIndex: 'svg', width: 130, render: (s: string) => <MolSvg svg={s} /> },
          { title: t('common.name'), dataIndex: 'name', render: (n: string, r: Json) => <Link to={`/database/${r.id}`}>{n || `#${r.id}`}</Link> },
          { title: 'conf.', dataIndex: 'confidence', width: 70 },
          { title: t('entry.issues'), dataIndex: 'issues', render: (is: string[]) => <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>{(is || []).slice(0, 3).map((s) => <li key={s}>{s}</li>)}</ul> },
          { title: t('common.status'), dataIndex: 'curation_status', render: (s: string) => <StatusTag status={s} /> },
          {
            title: t('common.actions'),
            render: (_: unknown, r: Json) => (
              <Space>
                <Button size="small" type="primary" onClick={() => setEntryStatus(r.id, 'verified')}>
                  {t('admin.verify')}
                </Button>
                <Button size="small" danger onClick={() => setEntryStatus(r.id, 'rejected')}>
                  {t('admin.reject')}
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}

function AddEntry() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [form] = Form.useForm();
  const [ref, setRef] = useState<Json | null>(null);
  const [cif, setCif] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const fetchDoi = async () => {
    const doi = form.getFieldValue('doi');
    try {
      setRef(await api.post('/curation/references/from-doi', { doi }));
    } catch (e: any) {
      message.error(e.message);
    }
  };
  const submit = async (v: Json) => {
    setBusy(true);
    try {
      const body: Json = {
        ...v,
        ccdc_numbers: (v.ccdc || '').split(/[\s,;]+/).filter(Boolean),
        solvents: (v.solvents || '').split(/[,;]+/).map((s: string) => s.trim()).filter(Boolean),
      };
      delete body.ccdc;
      const e = await api.post('/curation/entries', body);
      if (cif) {
        const fd = new FormData();
        fd.append('file', cif);
        fd.append('analyze', 'true');
        await api.upload(`/curation/entries/${e.id}/cif`, fd);
      }
      message.success(t('common.save'));
      nav(`/database/${e.id}`);
    } catch (err: any) {
      message.error(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Form form={form} layout="vertical" onFinish={submit} initialValues={{ components: [{ role: 'tecton', stoichiometry: 1 }], curation_status: 'verified' }} style={{ maxWidth: 900 }}>
      <Row gutter={14}>
        <Col span={12}>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input placeholder="HOF-xx" />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item label="DOI">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="doi" noStyle>
                <Input placeholder="10.xxxx/…" />
              </Form.Item>
              <Button onClick={fetchDoi}>{t('admin.fetchDoi')}</Button>
            </Space.Compact>
          </Form.Item>
        </Col>
      </Row>
      {ref ? <Alert type="success" style={{ marginBottom: 12 }} message={<Citation refd={ref} compact />} /> : null}
      <Form.List name="components">
        {(fields, { add, remove }) => (
          <Card size="small" title={t('entry.components')} extra={<Button size="small" icon={<PlusOutlined />} onClick={() => add({ role: 'co_tecton', stoichiometry: 1 })}>{t('admin.addComponent')}</Button>} style={{ marginBottom: 14 }}>
            {fields.map((f) => (
              <Row gutter={10} key={f.key} align="top">
                <Col span={13}>
                  <Form.Item name={[f.name, 'smiles']} rules={[{ required: true }]}>
                    <SmilesInput />
                  </Form.Item>
                </Col>
                <Col span={4}>
                  <Form.Item name={[f.name, 'role']}>
                    <Select options={['tecton', 'co_tecton', 'counterion', 'template'].map((r) => ({ value: r, label: r }))} />
                  </Form.Item>
                </Col>
                <Col span={3}>
                  <Form.Item name={[f.name, 'stoichiometry']}>
                    <InputNumber min={0.01} step={0.5} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={3}>
                  <Form.Item name={[f.name, 'name']}>
                    <Input placeholder={t('common.name')} />
                  </Form.Item>
                </Col>
                <Col span={1}>
                  <MinusCircleOutlined onClick={() => remove(f.name)} style={{ marginTop: 10 }} />
                </Col>
              </Row>
            ))}
          </Card>
        )}
      </Form.List>
      <Row gutter={14}>
        <Col span={8}>
          <Form.Item name="ccdc" label={t('entry.ccdc')}>
            <Input placeholder="1234567, …" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="topology" label={t('db.topology')}>
            <Input placeholder="dia / sql / hcb …" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="hbond_class" label={t('db.hbondClass')}>
            <Input placeholder="carboxy / dat / …" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="solvents" label={t('entry.solvents')}>
            <Input placeholder="DMF, ethanol" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="temperature" label={t('entry.temperature')}>
            <Input placeholder="rt / 90 °C" />
          </Form.Item>
        </Col>
        <Col span={8}>
          <Form.Item name="bet_m2_g" label="BET (m²/g)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      <Form.Item name="application" label={t('entry.application')}>
        <Input />
      </Form.Item>
      <Form.Item name="notes" label={t('entry.notes')}>
        <Input.TextArea rows={2} />
      </Form.Item>
      <Row gutter={14}>
        {['activation_retained', 'measured_porosity'].map((k) => (
          <Col span={8} key={k}>
            <Form.Item name={['evidence', k, 'value']} label={t(`evidence.${k}`)}>
              <Select allowClear options={['yes', 'no', 'unknown'].map((v) => ({ value: v, label: t(`evidence.${v}`) }))} />
            </Form.Item>
          </Col>
        ))}
        <Col span={8}>
          <Form.Item name="curation_status" label={t('db.status')}>
            <Select options={['verified', 'needs_review', 'candidate'].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
          </Form.Item>
        </Col>
      </Row>
      <Form.Item label={t('admin.uploadCif')}>
        <Upload beforeUpload={(f) => { setCif(f); return false; }} maxCount={1} accept=".cif" onRemove={() => setCif(null)}>
          <Button icon={<UploadOutlined />}>{t('admin.uploadCif')}</Button>
        </Upload>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={busy}>
        {t('common.submit')}
      </Button>
    </Form>
  );
}

function Users() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ['users'], queryFn: () => api.get('/users') });
  const patch = async (id: number, body: Json) => {
    await api.patch(`/users/${id}`, body);
    qc.invalidateQueries({ queryKey: ['users'] });
  };
  const create = async (v: Json) => {
    try {
      await api.post('/users', v);
      setOpen(false);
      qc.invalidateQueries({ queryKey: ['users'] });
    } catch (e: any) {
      message.error(e.message);
    }
  };
  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => setOpen(true)}>
        {t('admin.newUser')}
      </Button>
      <Table
        rowKey="id"
        size="small"
        dataSource={q.data || []}
        columns={[
          { title: t('login.username'), dataIndex: 'username' },
          { title: t('common.name'), dataIndex: 'display_name' },
          { title: t('admin.role'), dataIndex: 'role', render: (r: string, u: Json) => <Select size="small" value={r} style={{ width: 120 }} onChange={(v) => patch(u.id, { role: v })} options={['admin', 'curator', 'member'].map((x) => ({ value: x, label: x }))} /> },
          { title: t('admin.active'), dataIndex: 'is_active', render: (a: boolean, u: Json) => <Switch size="small" checked={a} onChange={(v) => patch(u.id, { is_active: v })} /> },
        ]}
      />
      <Modal open={open} onCancel={() => setOpen(false)} footer={null} title={t('admin.newUser')} destroyOnHidden>
        <Form layout="vertical" onFinish={create} initialValues={{ role: 'member' }}>
          <Form.Item name="username" label={t('login.username')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="display_name" label={t('common.name')}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('login.password')} rules={[{ required: true, min: 8 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label={t('admin.role')}>
            <Select options={['admin', 'curator', 'member'].map((x) => ({ value: x, label: x }))} />
          </Form.Item>
          <Button type="primary" htmlType="submit">
            {t('common.save')}
          </Button>
        </Form>
      </Modal>
    </div>
  );
}

function CsdStatus() {
  const q = useQuery({ queryKey: ['csd'], queryFn: () => api.get('/curation/csd/status') });
  return q.data ? <Alert type={q.data.available ? 'success' : 'info'} showIcon message={q.data.available ? 'CSD Python API available' : 'CSD Python API not available'} description={q.data.detail} /> : null;
}

export default function AdminPage() {
  const { t } = useTranslation();
  const { isAdmin } = useAuth();
  return (
    <div>
      <PageHead title={t('admin.title')} />
      <Tabs
        items={[
          { key: 'q', label: t('admin.queue'), children: <Queue /> },
          { key: 'a', label: t('admin.addEntry'), children: <AddEntry /> },
          ...(isAdmin ? [{ key: 'u', label: t('admin.users'), children: <Users /> }] : []),
          { key: 'c', label: t('admin.csd'), children: <CsdStatus /> },
        ]}
      />
      <Tag style={{ display: 'none' }} />
    </div>
  );
}
