import { createContext, useContext, useState, ReactNode } from 'react';

interface AccountContextValue {
  accountId: string;
  setAccountId: (id: string) => void;
}

const AccountContext = createContext<AccountContextValue | null>(null);

interface AccountProviderProps {
  children: ReactNode;
  defaultAccountId?: string;
}

export function AccountProvider({ children, defaultAccountId = 'ACC001' }: AccountProviderProps) {
  const [accountId, setAccountId] = useState(defaultAccountId);

  return (
    <AccountContext.Provider value={{ accountId, setAccountId }}>
      {children}
    </AccountContext.Provider>
  );
}

export function useAccountId(): string {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error('useAccountId must be used within an AccountProvider');
  }
  return context.accountId;
}

export function useAccount(): AccountContextValue {
  const context = useContext(AccountContext);
  if (!context) {
    throw new Error('useAccount must be used within an AccountProvider');
  }
  return context;
}
