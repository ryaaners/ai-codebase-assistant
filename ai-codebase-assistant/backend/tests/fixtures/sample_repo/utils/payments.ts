import { ChargeClient } from "./charge_client";

export interface PaymentResult {
  success: boolean;
  transactionId: string;
}

export class PaymentService {
  private client: ChargeClient;

  constructor(client: ChargeClient) {
    this.client = client;
  }

  async processPayment(userId: string, amountCents: number): Promise<PaymentResult> {
    const charge = await this.client.charge(userId, amountCents);
    return formatResult(charge);
  }
}

export const formatResult = (charge: any): PaymentResult => {
  return { success: charge.ok, transactionId: charge.id };
};

function unusedFormatter(x: number): string {
  return x.toFixed(2);
}
