import React from 'react'

const Search = () => {
    const fieldClass = "flex-1 min-w-36 px-3 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-800 bg-gray-50 outline-none cursor-pointer";
    return (
        <div className="bg-white rounded-xl shadow-md max-w-3xl mx-auto p-3 flex items-center gap-2 flex-wrap">
            <select className={fieldClass}>
                <option>Palamos, Spain</option>
                <option>Barcelona, Spain</option>
                <option>Paris, France</option>
            </select>

            <input type="date" defaultValue="2025-08-24" className={fieldClass} />

            <input type="date" defaultValue="2025-09-01" className={fieldClass} />

            <select className={fieldClass}>
                <option>1 adult, 1 room</option>
                <option>2 adults, 1 room</option>
                <option>2 adults, 2 rooms</option>
            </select>

            <button className="bg-blue-500 hover:bg-blue-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg cursor-pointer transition-colors">
                Search
            </button>
        </div>
    );
}

export default Search