import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'

export default function Results() {
	// State for API response and loading status
	const [searchParams] = useSearchParams();
	const [results, setResults] = useState([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);

	// Reads URL then performs fetch request
	useEffect(() => {
		const fetchResults = async () => {
			setLoading(true);
			try {
				// Fetch results using the current URL's search params
				const response = await fetch(`/search?${searchParams.toString()}`);

				if (!response.ok) throw new Error('Failed to fetch recommendations');

				const data = await response.json();

				// We access the 'gifts' key we defined in our FastAPI return statement
				setResults(data.gifts || []);
			} catch (error) {
				setError("Error connecting to backend: " + error.message);
			} finally {
				setLoading(false);
			}
		};
		fetchResults();
	}, [searchParams]); // Re-run when search params change

	return (
		// Displays list of results
		<div style={{ padding: '20px' }}>
			<Link to="/">← Back to Search</Link>
			<h2>Search Results</h2>
			{loading && <p>Searching...</p>}
			{error && <p style={{ color: 'red' }}>{error}</p>}

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
	);
}