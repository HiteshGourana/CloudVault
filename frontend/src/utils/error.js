/**
 * Extracts a user-friendly string error message from an API response error.
 * Handles FastAPI/Pydantic list of validation errors, string details, and fallback messages.
 *
 * @param {Error} err - The catch block error object.
 * @param {string} defaultMessage - Fallback message if no detail can be extracted.
 * @returns {string} Fully readable string error message.
 */
export const extractErrorMessage = (err, defaultMessage = 'An unexpected error occurred.') => {
  const detail = err.response?.data?.detail;
  
  if (!detail) {
    return err.message || defaultMessage;
  }
  
  if (typeof detail === 'string') {
    return detail;
  }
  
  if (Array.isArray(detail)) {
    // For Pydantic validation list, format them e.g. "email: value is not a valid email address"
    return detail
      .map(d => {
        const fieldName = d.loc && d.loc.length > 1 ? d.loc.slice(1).join('.') : '';
        return fieldName ? `${fieldName}: ${d.msg}` : d.msg;
      })
      .join(' | ');
  }
  
  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail);
  }
  
  return defaultMessage;
};
