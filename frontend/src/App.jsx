import { useState } from 'react'
// import reactLogo from './assets/react.svg'
// import viteLogo from '/vite.svg'
// import './App.css'

function App() {
  // state for form inputs to access data, sets default values for testing
  const [formData, setFormData] = useState({
	recipient: '',
	minPrice: null,
	maxPrice: null,
	query: ''
  });
  // State for API response and loading status
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Search function
  const handleSearch = async (e) => {
	e.preventDefault();		// prevent page refresh on form submit
	setLoading(true);
	setError(null);

	try {
	  // Constructing the URL with & separators as required by FastAPI
      // We use URLSearchParams to handle encoding (e.g., spaces to %20) automatically
      const params = new URLSearchParams({
        recipient: formData.recipient,
        min_price: formData.minPrice,
        max_price: formData.maxPrice,
        q: formData.query
	  });

	  //const url = 'http://localhost:8000/search?recipient=${formData.recipient}&min_price=${formData.minPrice}&max_price=${formData.maxPrice}&q=${formData.query}';
	  const response = await fetch(`http://localhost:8000/search?${params.toString()}`);

	  if (!response.ok) throw new Error('Failed to fetch recommendations');

	  const data = await response.json();
		
	  // We access the 'gifts' key we defined in our FastAPI return statement
	  setResults(data.gifts || []);
	} catch (error) {
	  setError("Error connecting to backend: " + error.message);
	}
	finally {
	  setLoading(false);
	}
  };

  return (
	<div style={{ 
	  display: 'flex',
	  flexDirection: 'column',
	  alignItems: 'center',		// centers horizontally
	  justifyContent: 'center',	// centers vertically
	  minHeight: '100vh',		// sets height to full screen
	  width: '100vw',
	  padding: '20px', 
	  fontFamily: 'system-ui',
	  boxSizing: 'border-box',
	}}>
      <header style={{ textAlign: 'center', marginBottom: '40px' }}>
        <h1>Personalized Gift Recommender for Every Occasion</h1>
      </header>

      {/* --- Search Form --- */}
      <form onSubmit={handleSearch} style={{
		width: '100%',
		maxWidth: '500px', 
		display: 'grid', 
		gap: '20px', 
		background: '#f8f9fa', 
		padding: '20px', 
		borderRadius: '12px',
		boxShadow: '0 4px 6px rgba(0,0,0,0.1)' // Optional: adds a nice lift 
	  }}>
        <div>
          <label style={{ display: 'block', fontWeight: 'bold' }}>Who is the recipient?</label>
          <select 
            value={formData.recipient}
            onChange={(e) => setFormData({...formData, recipient: e.target.value})}
            style={{ width: '100%', padding: '10px', marginTop: '5px' }}
          >
            <option value = "">Select a recipient...</option>
            <option value="mom">Mom</option>
            <option value="dad">Dad</option>
            <option value="friend">Friend</option>
            <option value="colleague">Colleague</option>
          </select>
        </div>

        <div style={{ display: 'flex', gap: '20px' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontWeight: 'bold' }}>Min Price ($)</label>
            <input 
              type="number" 
              placeholder="Min e.g. 10"
              value={formData.minPrice}
              onChange={(e) => setFormData({...formData, minPrice: e.target.value})}
              style={{ width: '95%', padding: '10px' }} 
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontWeight: 'bold' }}>Max Price ($)</label>
            <input 
              type="number" 
              placeholder="Max e.g. 1000"
              value={formData.maxPrice}
              onChange={(e) => setFormData({...formData, maxPrice: e.target.value})}
              style={{ width: '95%', padding: '10px' }} 
            />
          </div>
        </div>

        <div>
          <label style={{ display: 'block', fontWeight: 'bold' }}>What are they interested in?</label>
          <input 
            type="text" 
            placeholder="e.g. video games, cooking, gardening"
            value={formData.query}
            onChange={(e) => setFormData({...formData, query: e.target.value})}
            style={{ width: '95%', padding: '10px', marginTop: '5px' }}
          />
        </div>

        <button 
          type="submit" 
          disabled={loading}
          style={{ 
            backgroundColor: '#007bff', color: 'white', padding: '12px', 
            border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' 
          }}
        >
          {loading ? 'Searching...' : 'Find Perfect Gift'}
        </button>
      </form>

      {/* --- Results Section --- */}
      <div style={{ width: '100%', maxWidth: '800px', marginTop: '40px' }}>
        {error && <p style={{ color: 'red' }}>Error: {error}</p>}

        {results.length > 0 ? (
          <div style={{ 
			display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '15px' }}>
            {results.map((gift, index) => (
              <div key={index} style={{ border: '1px solid #ddd', padding: '15px', borderRadius: '8px' }}>
                <h3 style={{ fontSize: '1.1rem', 
  				  marginBottom: '8px',
  				  display: '-webkit-box',
  				  WebkitLineClamp: '2',      // Limit to 2 lines
  				  WebkitBoxOrient: 'vertical',
  				  overflow: 'hidden',
  				  textOverflow: 'ellipsis',
  				  minHeight: '2.4em' }}>
					{gift.name}
				</h3>
                <p style={{ fontWeight: 'bold', color: '#28a745' }}>${gift.price.toFixed(2)}</p>
                <p style={{ fontSize: '0.9rem', color: '#666' }}>Store: {gift.source.toUpperCase()}</p>
                <div style={{ fontSize: '0.8rem', background: '#e9ecef', padding: '5px', borderRadius: '4px', margin: '10px 0' }}>
                  Matched: {gift.matches.slice(0, 3).join(', ')}
                </div>
                <a href={gift.url} target="_blank" rel="noreferrer" style={{ color: '#007bff', textDecoration: 'none', fontWeight: 'bold' }}>
                  View Product →
                </a>
              </div>
            ))}
          </div>
        ) : (
          !loading && <p style={{ textAlign: 'center', color: '#888' }}>No results yet. Try a search!</p>
        )}
      </div>
    </div>
  );
}

export default App;