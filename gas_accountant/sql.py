import datetime as dt

def token_prices(token_addresses, network, start_date):
    start_date = dt.datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
    """
    Generate a SQL query to get historical price data for given token addresses from a specific start date.

    Parameters:
    - token_addresses (list): List of token addresses.
    - start_date (str): Start date in 'YYYY-MM-DD' format.

    Returns:
    - str: The SQL query string.
    """
    # Format the addresses into the SQL VALUES clause
    addresses_clause = ", ".join(f"(LOWER('{address}'))" for address in token_addresses)

    beginning = f"'{start_date.strftime('%Y-%m-%d %H:%M:%S')}'"
    print('Beginning:', beginning)
    
    prices_query = f"""
    WITH addresses AS (
        SELECT column1 AS token_address 
        FROM (VALUES
            {addresses_clause}
        ) AS tokens(column1)
    )

    SELECT 
        hour,
        symbol,
        price
    FROM 
        {network}.price.ez_prices_hourly
    WHERE 
        token_address IN (SELECT token_address FROM addresses)
        AND hour >= DATE_TRUNC('hour', TO_TIMESTAMP({beginning}, 'YYYY-MM-DD HH24:MI:SS'))
    ORDER BY 
        hour DESC, symbol
    """

    return prices_query