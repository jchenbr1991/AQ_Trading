// frontend/src/components/BacktestForm.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BacktestForm } from './BacktestForm';

describe('BacktestForm', () => {
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all form fields', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={false} />);

    expect(screen.getByLabelText(/symbol/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/initial capital/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/lookback period/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/threshold/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/position size/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/slippage/i)).toBeInTheDocument();
  });

  it('renders submit button', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={false} />);

    expect(screen.getByRole('button', { name: /run backtest/i })).toBeInTheDocument();
  });

  it('shows loading state when isLoading is true', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={true} />);

    const button = screen.getByRole('button', { name: /running backtest/i });
    expect(button).toBeDisabled();
  });

  it('calls onSubmit with form data when submitted', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={false} />);

    // Fill in the form with custom values
    fireEvent.change(screen.getByLabelText(/symbol/i), { target: { value: 'MSFT' } });
    fireEvent.change(screen.getByLabelText(/initial capital/i), { target: { value: '50000' } });
    fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: '2024-06-01' } });
    fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2024-12-01' } });
    fireEvent.change(screen.getByLabelText(/lookback period/i), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText(/threshold/i), { target: { value: '1.5' } });
    fireEvent.change(screen.getByLabelText(/position size/i), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText(/slippage/i), { target: { value: '10' } });

    // Submit the form
    fireEvent.click(screen.getByRole('button', { name: /run backtest/i }));

    expect(mockOnSubmit).toHaveBeenCalledWith({
      strategy_class: 'MeanReversionStrategy',
      strategy_params: {
        lookback_period: 30,
        threshold: 1.5,
        position_size: 50,
      },
      symbol: 'MSFT',
      start_date: '2024-06-01',
      end_date: '2024-12-01',
      initial_capital: '50000',
      slippage_bps: 10,
    });
  });

  it('converts symbol to uppercase', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={false} />);

    const symbolInput = screen.getByLabelText(/symbol/i);
    fireEvent.change(symbolInput, { target: { value: 'goog' } });

    expect(symbolInput).toHaveValue('GOOG');
  });

  it('has default values pre-filled', () => {
    render(<BacktestForm onSubmit={mockOnSubmit} isLoading={false} />);

    expect(screen.getByLabelText(/symbol/i)).toHaveValue('AAPL');
    expect(screen.getByLabelText(/initial capital/i)).toHaveValue(100000);
    expect(screen.getByLabelText(/lookback period/i)).toHaveValue(20);
    expect(screen.getByLabelText(/threshold/i)).toHaveValue(2);
    expect(screen.getByLabelText(/position size/i)).toHaveValue(100);
    expect(screen.getByLabelText(/slippage/i)).toHaveValue(5);
  });
});
