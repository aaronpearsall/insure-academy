/**
 * CII Insurance Qualifications Framework - units with credits and study hours.
 * Source: CII 2026 qualifications. Planning aid only; verify rules at cii.co.uk
 */

const CII_UNITS = {
  certificate: [
    { code: 'IF1', title: 'Insurance, Legal and Regulatory', credits: 15, studyHours: 60, rqf: 3, core: true },
    { code: 'IF2', title: 'General Insurance Business', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF3', title: 'Insurance Underwriting Process', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF4', title: 'Insurance Claims Handling Process', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF5', title: 'Motor Insurance Products', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF6', title: 'Household Insurance Products', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF7', title: 'Healthcare Insurance Products', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF8', title: 'Packaged Commercial Insurances', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'IF9', title: 'Customer Service in Insurance', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'I10', title: 'Insurance Broking Fundamentals', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'I11', title: 'Introduction to Risk Management', credits: 15, studyHours: 60, rqf: 3, core: false },
    { code: 'GR1', title: 'Group Risk', credits: 10, studyHours: 50, rqf: 3, core: false },
    { code: 'LM1', title: 'London Market Insurance Essentials', credits: 10, studyHours: 40, rqf: 3, core: true },
    { code: 'LM2', title: 'London Market Insurance Principles and Practices', credits: 15, studyHours: 60, rqf: 3, core: true },
    { code: 'LM3', title: 'London Market Underwriting Principles', credits: 15, studyHours: 60, rqf: 3, core: false },
  ],
  diploma: [
    { code: 'M05', title: 'Insurance Law', credits: 25, studyHours: 120, rqf: 4, core: true },
    { code: 'M21', title: 'Commercial Insurance Contract Wording', credits: 20, studyHours: 100, rqf: 4, core: false },
    { code: 'M66', title: 'Delegated Authority', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M67', title: 'Fundamentals of Risk Management', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M80', title: 'Underwriting Practice', credits: 20, studyHours: 80, rqf: 4, core: false },
    { code: 'M81', title: 'Insurance Broking Practice', credits: 20, studyHours: 80, rqf: 4, core: false },
    { code: 'M85', title: 'Claims Practice', credits: 20, studyHours: 80, rqf: 4, core: false },
    { code: 'M86', title: 'Personal Insurances', credits: 20, studyHours: 80, rqf: 4, core: false },
    { code: 'M90', title: 'Cargo and Goods in Transit Insurances', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M91', title: 'Aviation and Space Insurance', credits: 30, studyHours: 120, rqf: 4, core: false },
    { code: 'M92', title: 'Insurance Business and Finance', credits: 25, studyHours: 100, rqf: 4, core: true },
    { code: 'M93', title: 'Commercial Property and Business Interruption Insurances', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M94', title: 'Motor Insurance', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M96', title: 'Liability Insurances', credits: 25, studyHours: 100, rqf: 4, core: false },
    { code: 'M97', title: 'Reinsurance', credits: 30, studyHours: 120, rqf: 4, core: false },
    { code: 'M98', title: 'Marine Hull and Associated Liabilities', credits: 30, studyHours: 100, rqf: 4, core: false },
  ],
  advanced: [
    { code: '530', title: 'Economics and Business', credits: 30, studyHours: 150, rqf: 6, core: true },
    { code: '820', title: 'Advanced Claims', credits: 30, studyHours: 150, rqf: 6, core: true },
    { code: '930', title: 'Advanced Insurance Broking', credits: 30, studyHours: 150, rqf: 6, core: true },
    { code: '945', title: 'Marketing Insurance Products and Services', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '960', title: 'Advanced Underwriting', credits: 30, studyHours: 150, rqf: 6, core: true },
    { code: '990', title: 'Insurance Corporate Management', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '992', title: 'Risk Management in Insurance', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '995', title: 'Strategic Underwriting', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '996', title: 'Strategic Claims Management', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '997', title: 'Advanced Risk Financing and Transfer', credits: 30, studyHours: 150, rqf: 6, core: false },
    { code: '993', title: 'Advances in Strategic Risk Management in Insurance', credits: 50, studyHours: 180, rqf: 6, core: false },
    { code: '991', title: 'London Market Insurance Specialisation', credits: 50, studyHours: 180, rqf: 7, core: false },
    { code: '994', title: 'Insurance Market Specialisation', credits: 50, studyHours: 180, rqf: 8, core: false },
  ],
};

const QUALIFICATION_RULES = {
  certificate: {
    minCredits: 40,
    coreRule: 'IF1 (15) OR (LM1 + LM2 = 25)',
    checkCore: (passed) => {
      const codes = new Set(passed.map(p => p.code));
      if (codes.has('IF1')) return true;
      if (codes.has('LM1') && codes.has('LM2')) return true;
      return false;
    },
  },
  diploma: {
    minTotal: 120,
    minDiplomaPlus: 90,
    coreRule: 'M05 + (M92 OR 530)',
    checkCore: (passed) => {
      const codes = new Set(passed.map(p => p.code));
      if (!codes.has('M05')) return false;
      if (codes.has('M92') || codes.has('530')) return true;
      return false;
    },
  },
  advanced: {
    minTotal: 290,
    minAdvanced: 150,
    minDiplomaPlus: 55,
    coreRule: 'M05 + (M92 OR 530) + (820 OR 930 OR 960)',
    checkCore: (passed) => {
      const codes = new Set(passed.map(p => p.code));
      if (!codes.has('M05')) return false;
      if (!codes.has('M92') && !codes.has('530')) return false;
      if (codes.has('820') || codes.has('930') || codes.has('960')) return true;
      return false;
    },
  },
};
