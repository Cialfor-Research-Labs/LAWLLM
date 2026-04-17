export type GeneratorTone = 'firm' | 'aggressive' | 'polite';

export interface GeneratorPrefillPayload {
  senderName: string;
  receiverName: string;
  senderAddress: string;
  receiverAddress: string;
  relationship: string;
  facts: string[];
  claim: string;
  noticeType: string;
  tone: GeneratorTone;
  deadline: number | '';
  customRelief: string;
  sourceSessionId?: string;
  sourceSummary?: string;
}

export interface GeneratorPrefillRequest {
  payload: GeneratorPrefillPayload;
  nonce: number;
}
