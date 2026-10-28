import type { ThemeConfig } from 'antd';

export const brand = {
  ink: '#111418',
  paper: '#F6F4EF',
  paper2: '#FBFAF7',
  indigo: '#1E2A3A',
  gold: '#B08D57',
  line: '#E4DED2',
};

export const theme: ThemeConfig = {
  token: {
    colorPrimary: brand.indigo,
    colorInfo: brand.indigo,
    colorLink: '#7A5C2E',
    colorLinkHover: brand.gold,
    colorSuccess: '#3F6B4F',
    colorWarning: '#A8742A',
    colorError: '#9B3B32',
    colorText: brand.ink,
    colorTextSecondary: '#5B6067',
    colorBgLayout: brand.paper,
    colorBgContainer: '#FFFFFF',
    colorBorder: '#DDD6C8',
    colorBorderSecondary: brand.line,
    borderRadius: 3,
    borderRadiusLG: 4,
    borderRadiusSM: 2,
    fontFamily: 'var(--font-sans)',
    fontFamilyCode: 'var(--font-mono)',
    fontSize: 14,
    controlHeight: 34,
    boxShadow: '0 4px 18px rgba(17,20,24,0.06)',
  },
  components: {
    Layout: { headerBg: brand.paper2, headerHeight: 64, headerPadding: '0 28px', bodyBg: brand.paper, footerBg: brand.paper },
    Menu: { itemBg: 'transparent', horizontalItemSelectedColor: brand.ink, itemSelectedColor: brand.ink, activeBarHeight: 2 },
    Card: { headerFontSize: 16, colorBorderSecondary: brand.line },
    Button: { primaryShadow: 'none', defaultShadow: 'none', fontWeight: 500 },
    Table: { headerBg: '#F3F0E9', headerColor: brand.ink, rowHoverBg: '#FAF7F1' },
    Tag: { defaultBg: '#F3F0E9' },
    Tabs: { inkBarColor: brand.gold, itemSelectedColor: brand.ink, itemHoverColor: brand.ink },
    Statistic: { contentFontSize: 30 },
  },
};
