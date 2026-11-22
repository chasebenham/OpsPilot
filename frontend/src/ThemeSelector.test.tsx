// @vitest-environment jsdom
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {ThemeSelector} from './ThemeSelector';

afterEach(()=>{cleanup();localStorage.clear();delete document.documentElement.dataset.theme});
it('switches and persists the appearance',async()=>{
 render(<ThemeSelector/>);
 await userEvent.selectOptions(screen.getByLabelText('Appearance'),'dark');
 expect(document.documentElement.dataset.theme).toBe('dark');
 expect(localStorage.getItem('opspilot-theme')).toBe('dark');
 cleanup();render(<ThemeSelector/>);
 expect((screen.getByLabelText('Appearance') as HTMLSelectElement).value).toBe('dark');
});
